---
name: handoff
description: "Mid-workstream save-state under context pressure — always a continuation."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session Handoff — Save State for Next Session

> **Handoff is involuntary by definition — with exactly two sanctioned deliberate triggers.** The baseline is context pressure that forces the current session to stop mid-workstream before its next action can land. A handoff is a continuation-point, not a workstream-ending ceremony — if you find yourself reaching for `/handoff` because the work feels like a good place to pause, that framing IS the disqualifier. Workstreams end via `/workday-complete`, `/merge-to-main`, or `/quick-wrap` (the commit-and-stop close); never via handoff. The EM does not voluntarily invoke this skill at perceived stopping points. **The first named exception: the plan→execute execution handoff.** When review-integration has completed and the plan carries the PM's `execution_authorized_at` stamp, deliberately handing off to a fresh execution session is the empirically-superior next action (context saturation degrades execution reliability), not a tidy-pause deferral — this trigger is legitimate independent of context pressure. **The second: the review-owed close handoff** (§ Step 0), which fires only under genuine context pressure, same as the baseline. Both are *specific, gated* triggers, not a general license to hand off at any tidy point — every other trigger below remains involuntary-only.

> **Continuation vs. fork.** This skill writes a *continuation* handoff — work the current session was doing that someone (often you, next session) will resume. To carve off a *different* mid-session topic for someone else to pick up cold, use `/spinoff` instead — that produces `kind: spinoff`, `predecessor: none` handoffs, designed for fork rather than continuation. **A next *phase* of the same multi-phase workstream (research → goal-setting → plan → execute → verify) is a continuation, not a fork — even when the phase boundary looks topically distinct.** The next stage of *this* workstream is never a `/spinoff`; `/spinoff` is reserved for a genuinely *different* workstream. Do NOT redirect a legitimate phase-transition handoff to `/spinoff` because the incoming phase reads as a new topic — the topic boundary is illusory; the workstream is the same one, mid-arc.

The assembler computes the mechanical spine — deliverable/initiative id inheritance (plan → predecessor → mint), frontmatter scaffolding, `handoff_phase` stamping, tracker refresh, and (on a clean chain) predecessor archival — and returns one decision object per handoff. What follows is the judgment residue the assembler cannot resolve for you: it narrows the evidence, you decide.

Compute it via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/baton-assemble" brief handoff <artifact-path>`.

**`<artifact-path>` is the artifact this handoff is being written FROM, and on the plan→execute trigger that is the PLAN, not a handoff.** The deliverable-id cascade (plan → predecessor → mint) can only reach its first arm if the plan path is what you hand `brief`; pass a handoff — or pass nothing, which self-resolves to the held handoff — and it silently falls through to the predecessor's id or a fresh mint off the handoff's own title slug. The plan and the handoff executing it then carry different `deliverable_id`s, the join is exact-string-equality, and close-out stamping reports a fully-shipped plan as entirely unshipped. On an ordinary continuation the held handoff IS the right artifact and the default is correct; the plan→execute seam is the case where the default is wrong and silent — measured across an engine-plane corpus at better than four plans in five.

Every `judgment_points[]` entry in the returned object carries its own guidance inline — describing what each disposition means and how to carry it out, never a recommendation to pick from; resolve each one before its gated directive(s) proceed.

Feed those resolutions back by passing `--decisions` to `apply`: a JSON object mapping each `judgment_points[].id` to `{"disposition": "<value>"}`. The legal values for a given point are that point's own `dispositions[].value` entries from the same run's `brief` output — read them there rather than guessing. `{"value": "<v>"}` is accepted as an exact equivalent of `{"disposition": "<v>"}`, and sibling keys (a `decision_note`, for instance) are carried through; supplying both keys with disagreeing values fails loud.

**`brief` computes; `apply` writes — run it, never hand-execute the directive list.** `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/baton-assemble" apply handoff <artifact-path> --decisions '<json>'` — the same `<artifact-path>` you gave `brief`, plus the resolutions above. Measured fleet-wide across July and August, `apply` was invoked for 130 of 959 non-spinoff handoffs; the other 86% hand-authored the successor, and `d6` (`handoff.supersede_predecessor`) — last in the directive list, and the only write that flips the predecessor to `continued` — never fired. That is the dominant source of stranded batons: shipped work still advertising itself as in flight. A brief whose directives you transcribe by hand has discharged nothing; it relocated the transcription, and the hand-execution reliably stops before the last directive.

---

## Step 0: Trigger Check — Is Context Pressure Actually Forcing This?

Before writing anything, run this binary gate. The PRIMARY question is whether the current session can still take its next action; if it can, you are not handing off, you are deferring — and that's a doctrine violation regardless of how "tidy" the current state looks.

### Trigger gate — at least one must be true → continue

- Auto-compaction is imminent or in progress and would lose load-bearing context before the next action can land.
- A Claude Code restart or MCP-bridge restart is unavoidable mid-workstream.
- A hard blocker (PM input, external system, after-hours wait) is preventing the next action *right now* — not a future step.
- The PM has explicitly invoked `/handoff` and named the workstream. **Literal trigger only** — "you can hand that off," "let's pass this to the next session," or "another session will finish it" are intent-descriptions, not invocations. The authorizing act is the PM typing `/handoff` (or the skill name) for *this* workstream, OR one of the first three context-pressure conditions above firing involuntarily. Do not promote an intent-shaped remark into a voluntary handoff.
- **Review-owed close handoff (the trampoline out of `/workstream-complete`):** `/workstream-complete` named a review scale — most often partition-mandatory — that this session's remaining context cannot run *and* integrate. The successor's remit is to run that review and then cap. **Gated on context alone:** with context to spare the review belongs in this session, and reaching for this bullet to avoid a tedious four-reviewer dispatch is the deferral trap wearing a ceremony costume. Under genuine pressure it is the *only* sanctioned exit — the alternative is capping with the review unrun, which `/workstream-complete` forbids outright. **Name the signal:** the handoff body must state the concrete context signal that fired the gate — remaining context, turns since compaction, whatever was actually observed — so a peer, reviewer, or PM can later tell a real trampoline from ordinary deferral wearing its costume.
- **Plan→execute execution handoff (the one sanctioned deliberate trigger):** review-integration has completed for a plan AND that plan's frontmatter carries `execution_authorized_at` (the PM approved execution — set at the `coordinator:review` Exit gate). This is legitimate *independent of context pressure* — the fresh execution session is the empirically-superior next action, not a general tidy-pause license. Absent the stamp, this bullet does not fire.

If none of these hold, STOP. Take the next action in this session instead. "Plan reviewed," "looks like a good pause point," "feels tidy here" are not triggers — they are the trap.

### NO-tests — any one of these → STOP, do not write a handoff (even under context pressure, redirect to the right artifact)

- The workstream's next action is `/merge-to-main`, or the terminal PR is already merged with no follow-up commits expected.
- The work is described in your head as "shipped," "complete on branch ready for merge," or "ready for the merge gate." That phrasing IS the disqualifier — run `/quick-wrap` and stop, not a handoff. **Carve-out — a completed *phase* of an in-flight, *named* multi-phase workstream is NOT "shipped."** Committed artifacts from a finished phase (e.g. research committed and ready for `/goal-setting`) are phase *output*, not a shipped workstream. The disqualifier is *the whole workstream is shipped/merged with no next phase* — NOT *a phase artifact is committed*. If the workstream is mid-arc and a successor must run the next phase, this NO-test does not trip; continue; the phase-transition YES-test below is the relevant one when you reach YES-tests.
- All in-flight chunks of the active plan have landed and the plan doc is marked complete. **Carve-out — a workstream whose owed review has not been run is not "complete."** If `/workstream-complete` named a review scale this session cannot afford (§ trigger gate, review-owed close), the landed chunks are irrelevant: the ceremony is unfinished and this NO-test does not trip.
- **Plan is reviewed/approved but the executor hasn't been dispatched yet in this session — UNLESS the plan carries the `execution_authorized_at` stamp.** A reviewed plan is scaffolding, not a deliverable — the next action belongs in *this* session (dispatch the executor), not in a successor's. If acceptance criteria are still empirically unverified and no executor has run, STOP — dispatch, don't hand off. Handoff is legitimate only after the executor has run and there is genuine in-progress executor/integrator/test work for a successor to resume. **For the plan→execute trigger specifically, the `execution_authorized_at` stamp is the discriminator that decides which branch applies:**
  - **Un-stamped (plan reviewed/approved but the PM has not authorized execution):** this NO-test trips as written above — STOP, dispatch the executor in this session, do not hand off. "Looks tidy at plan-approval" is still the trap.
  - **Stamped (`execution_authorized_at` present):** this NO-test does NOT trip. The sanctioned plan→execute execution handoff (trigger-gate bullet above) applies instead — write the handoff, a successor session dispatches the executor via `/execute-plan`. This is the PM-authorized default outcome of review-integration, satisfying the anti-deferral rule because the *next action* genuinely belongs to the fresh session, not this one.
  - **Un-stamped, but a genuine phase-transition trigger-gate condition independently fires** (imminent compaction, unavoidable restart, or explicit PM `/handoff` invocation) **and a successor session will run the execute phase in fresh context:** this NO-test does NOT trip either — the pre-existing general phase-transition carve-out, not a special case of the stamp discriminator above; see the phase-transition YES-test below.
- **You are also planning to invoke `/workstream-complete` for this same workstream.** `/handoff` and `/workstream-complete` are mutually exclusive — never combined. `/workstream-complete` caps a workstream that is *done*; `/handoff` passes an *in-flight* workstream to a successor. The same workstream cannot be both. If the work is finished, STOP and run `/workstream-complete` alone. If it is in-flight, run `/handoff` alone. If you genuinely have two workstreams (one finished, one in-flight), end the finished one with `/workstream-complete` *separately*, naming it explicitly, then write the in-flight handoff here for the other one — never bundle the two surfaces in one closing motion. **Carve-out — the review-owed close handoff is not a bundling.** When `/workstream-complete` trampolines out under low context, you are not running both surfaces: you are running *neither* here, and handing the whole ceremony — review, then cap — to the successor. The mutual exclusion this NO-test protects is against capping and handing off the same workstream at once; deferring the cap entirely is the opposite motion, and this NO-test does not trip.
- **The handoff you would write is shipped work with no successor to pick it up.** That combination signals the EM reached for `/handoff` as a generic session-summary template when the right surface is `/workstream-complete` (review trail + queue triage + archival sweep) or `/workday-complete` (daily ceremony). The handoff pipeline treats every file in `state/handoffs/` as in-flight work — a shipped handoff shows up where it does not belong and pollutes triage in concurrent sessions. STOP — write the artifact for finished work, not a handoff for it. **Carve-out — a review-owed close handoff has a successor and a named remit** (run the owed review, then cap), so the "no successor to pick it up" half of this test fails and it does not trip. Say the remit in the handoff's `summary:` so triage reads it as the in-flight work it is.

### YES-tests — only consulted if all NO-tests fail

- In-progress edits not yet at a stopping point, AND a successor session must resume them.
- A plan in flight with remaining unexecuted chunks (not chunks that just landed in this session).
- Open blockers requiring PM input that arrived after-hours.
- A Claude Code restart imminent AND work in flight that the post-restart session must resume.
- PR open with reviewer feedback expected or unaddressed (iteration round counts as in-progress).
- **Phase transition in a multi-phase workstream.** The current session completed one phase of a named multi-phase workstream (research → goal-setting → plan → execute → verify) and a successor must run the next phase. The prior phase's committed artifacts are the *input* to the next phase, not a shipped endpoint — this is a continuation, and a handoff for it is legitimate even though the prior phase "committed." Do not resist it toward `/spinoff`.

### If a NO-test trips → STOP

The right artifact is one of:
- `/workday-complete` — end-of-day ceremony
- Commit-and-stop — for mid-day completion of a workstream that's already merged or PR-ready
- `/workstream-complete` — if lessons need capture but no successor brief is needed

### If at least one YES-test fires AND no NO-test trips → continue

*Handoffs are mid-stream baton-passes, not end-of-session ceremony. Shipped ≠ handed-off.*

---

### Inverted antipattern — "I'll just append to the predecessor I picked up"

> Applies whenever the EM has picked up a handoff this session and is now deciding whether to write a successor. Read as a standalone callout, not a sub-decision of the YES-path.

The most common failure mode of this skill is **skipping it**: the picked-up predecessor (now `status: claimed`) is sitting right there, so the EM appends a progress block to its body and stops. **This is a doctrine violation, not a shortcut.** A claimed handoff is paper trail; the pickup index treats claimed handoffs as historical and will NOT surface them as live work — any progress stapled into the body is invisible to the next opener. If you are about to edit a `status: claimed` handoff body to record what you just did, **STOP and run this skill from the top** — the YES/NO gate above still applies. Enforced at the tool layer (tripwire `CONSUMED-HANDOFF-FROZEN`) — the override is reserved for recovery-flavor crash-invalidation notes and one-off paper-trail corrections, never progress appends.

---

## Step 1: Write the Handoff

Scaffold by running `baton-assemble apply` (see the assembler blurb above for the literal invocation), which executes the whole directive set as one transaction — `d1` `coordinator-doc-new`, `d2` `lint-frontmatter`, `d4` render the tracker, `d5` `session-claim-cli` release-artifact plan, `d6` `handoff.supersede_predecessor` (fires only when this brief names a predecessor, discharging the supersession flip described in § Supersession below). Then fill the body per the scaffold's canonical section skeleton (`## What Was Accomplished`, `## Current State`, `## Next Steps`, `## Session Ledger`). Write the file FIRST, before any git operation — it is the irreversible artifact under context pressure; everything downstream is recoverable from disk.

**`d5` releases, it never acquires.** Authoring a handoff is a relinquishment, not a claim — the author is handing the plan to a successor, so `d5` runs `session-claim-cli release-artifact plan` against this session's held claim, best-effort and holder-identity-checked (a session that isn't the holder no-ops to success rather than failing). Claim *acquisition* belongs to `/pickup` alone; any other surface that acquires makes "someone once touched this plan" indistinguishable from "someone is working on this right now," which is exactly the false-positive `claim-plan` exists to prevent.

**`distill_fate:` — resolved at authorship, not deferred to a later `/distill` re-derivation pass.** No op mechanizes this write yet (`d2` `lint-frontmatter` validates the field against schema, it does not set values) — queued as a tooling gap: `state/improvement-queue/2026-07-25-no-op-stamps-handoff-distill-fate-at-aut-092cf9e386ce.yaml`. The harvest-vs-delete call is cheapest right now, while you hold full context on what this handoff actually is. Same enum as `cross-repo-memo.schema.json`: `ephemeral` (routine checkpoint, superseded once picked up — the common case), `commitment` (this handoff itself IS the open loop until a gate closes), `ratification` (records a settled decision with no other durable home — prefer promoting to `docs/decisions/`/`docs/wiki/` and stamping `ephemeral` once promoted).

---

## Step 2.9: Refresh Orientation Documents

Close the read-write loop with `/workstream-start` and `/workday-start` — best-effort, skip if compaction is imminent (the handoff file is the priority).

- **Orientation cache pinboard** — a single append-or-omit line, not a body rewrite: `/handoff` does not author the cache or patch its sections (that's ceremony-writer territory). If the picker-upper of this handoff MUST see a piece of context that won't be obvious from the handoff body or a fresh ceremony regen, append one line via `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/regenerate-orientation-cache" --invoker handoff --pinboard-only "YYYY-MM-DD <writer-slug>: <one-line note>"`. Otherwise do nothing.
- **Project tracker** (`docs/project-tracker.md`) — on a queue-backed repo, this is already covered by the assembler's `d4` render directive above; verify it reflects this session's progressed items. On a repo whose tracker is hand-curated, `d4` may decline to render and report a degrade instead — that degrade is expected, not a problem to fix, and there is nothing rendered to verify. Do not read the *absence* of a degrade as proof the tracker was spared: where the render guard is still the narrow one, `d4` can overwrite a hand-curated tracker without surfacing anything. Either way, check the file itself, and update the hand-curated tracker yourself, by hand, if this session progressed items worth recording in it. Never respond to a `d4` degrade by loosening the render guard's truncation protection — on a hand-curated tracker that discards real content.
- **Action items** (`ACTION-ITEMS.md` / `docs/active/ACTION-ITEMS.md` / `docs/ACTION-ITEMS.md`, first match) — check off any items this session resolved.

Targeted patches to what this session touched, not regeneration — concurrency-safe.

---

## `/handoff` Does Not Review

**No review step lives here, by ruling.** A handoff is involuntary by Step 0's own definition —
context pressure forcing a stop mid-workstream — and the one thing a session that just proved it
is out of room cannot afford is spending a dispatch. That alone would argue for skipping under
pressure; the stronger reason is structural: the diff a handoff writes is **in flight**, and an
in-flight diff is the state least worth reviewing. Findings against half-finished work are noise
the successor has to re-adjudicate against whatever they actually finish. An in-flight diff is a
reason **not** to review, not merely a reason to defer — read it that way, not as a shortcut this
skill is taking that needs justifying.

Review ownership stays exactly where it already sits: `/workstream-complete`, `/quick-wrap`, and
`/workweek-complete`'s parallel gate, each of which fires against a settled diff. Do not
reintroduce a conditional version of this step (e.g. "only when the diff contains code") — that
shape was considered and rejected; the objection is to reviewing in-flight work at all, not to
the cost of reviewing docs.

---

## Dirty-Tree Case-(c) Disposition

The assembler's `j-dirty-tree-case-c` judgment point surfaces the fact (uncommitted paths) — computed by `coordinator_core.ops.dirty_tree_gate` (`dirty-tree-gate.py`), runnable directly before the terminating commit via `python3 "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/dirty-tree-gate" --terminator handoff`; attribution is yours. Classify every dirty path as (a) yours, (b) a named concurrent owner's, or (c) unattributable — and never terminate with a case-(c) path still dirty and unnamed. For a genuine (c):

1. **Commit with provenance** if the change is coherent and you can attribute it.
2. **Stash with provenance** if it is incoherent or risky to commit — name the stash so the next session can find and adjudicate it.
3. **Explicit "leave it owned by X"** only when you can now name the owner, converting it from case (c) to case (b).

Orphan `.tmp.<pid>.<nanos>` files are a special case (Edit-tool atomic-write crash) — diff against target before deleting; do not stash them blind.

---

## Safe-Commit Auto-Commit

Before hand-classifying the dirty tree above, run the auto-commit mechanism — it does the (a)/(b) attribution AND the commit+push mechanically, leaving only genuine case-(c) paths for your judgment. Run `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/safe-commit-offer"` (no `--dry-run`) — it computes this session's safe pathspec (this session's own touch-list claims, minus anything a live peer session's touch list also claims) and commits+pushes it, then prints what landed and why.

**No confirmation step, by explicit PM ruling — do not add one, including behind a flag.** "I get annoyed when I'm asked if there should be a commit or not. y'all are the engineers." Being asked whether to commit was itself the defect. Run it and report the outcome AFTER the fact — never gate the run on an EM/PM yes.

**Push is automatic, same call.** The mechanism composes the existing `ceremony.scoped_git_commit` push-with-retry — there is no separate push step and no separate flag; a landed commit is a pushed commit (or a reported `push_state` naming why not, e.g. no remote).

**Grouping: prefer your own judgment over the mechanical default when you have real context.** Bare invocation groups mechanically (by directory, short bounded subject, full path list in the commit body) — the right shape for an unattended/no-judgment trigger. When this session has just finished deliberate, describable work, author real per-group messages instead via `--groups-json <file>` (a JSON list of `{"paths": [...], "message": "..."}`) or `--message "<subject>"` for a single well-described group — grouping and describing "like an engineer would" is exactly this authored path, not the mechanical fallback. Either way, any path you name that ISN'T actually in this session's computed safe pathspec is silently dropped, never committed — the boundary is computed, not caller-widened.

**Frame this as a safety net, not the primary path.** Per the PM: "if I have to commit, it's a safety [net] because someone forgot to commit." The GOOD archaeological commits are the deliberate ones a session makes while it's still running (still author real commits for real chunks of work as you go) — this mechanism exists so nothing is lost when that didn't happen, not to replace it.

**Multi-session overlap on the SAME file is accepted collateral, not a defect this mechanism solves.** It does not attempt conflict resolution between two sessions that both touched one file; it exists to stop ONE session's commit from sweeping a peer's UNRELATED work, the motivating failure this mechanism closes.

**`excluded` paths still need the Dirty-Tree Case-(c) judgment above** — the mechanism narrows what needs attention, it does not replace the classification. A path excluded as `untouched by this session` may still be a genuine case-(c) needing commit/stash/explicit-ownership disposition; a path excluded as `owned by session <id>` is already case (b).

---

## Recommended-Next-Steps Durability

These rules apply specifically to `## Recommended Next Steps` and `## In-Progress Work` — not to `## Current State` or `## Files Modified This Session`, which legitimately carry procedural detail because they describe what *is*, not what to *do*.

1. **No file paths or line numbers in next-steps prose.** They go stale within hours. Reference subsystems and concepts instead. _Exception:_ when the path IS the artifact (e.g., "the plan at `docs/plans/<plan-name>.md`"), that's an identifier, not a procedural step.
2. **Behavioral, not procedural.** Describe *what* the next session needs to accomplish, not *how*. The "how" goes stale; the "what" is durable.
3. **Each next step is independently verifiable.** The picker should be able to confirm "done" without reading this handoff again.
4. **Explicit out-of-scope line.** End every `## Recommended Next Steps` section with an "Out of scope for next session" line, so a fresh-eyed picker doesn't gold-plate or drift.

**Predecessor identification.** The predecessor is whatever handoff *this session was opened with* — period:

1. Session started with `/pickup <handoff>` — that file is the predecessor. Canonical signal.
2. The PM explicitly named a handoff at session start.
3. Neither? This handoff has **no predecessor** — omit the `Continuing from` preamble, write standalone.

**"Most recent file in `state/handoffs/`" is a facile signal — do not use it.** Concurrent sessions across machines routinely produce adjacent handoffs that have nothing to do with each other. Adjacency is not ancestry. Picking the most recent timestamp corrupts the audit trail and incorrectly archives active work belonging to other workstreams.

**Cascading unresolved items (only when there IS a predecessor).** Any item in the predecessor's `## Recommended Next Steps` / `## Carried Forward` that this session did not complete carries forward into the new handoff's `## Carried Forward`, with its origin annotation preserved. Items leave the cascade only by completion or explicit PM dismissal — never silent drop.

**The prose `_(carried via N handoffs)_` annotation is not the count of record — `carried_items:` frontmatter is.** Free-form prose lets the count silently rot (measured: items reached seven and eight consecutive carries behind exactly that annotation before being forked). Every `## Carried Forward` entry that is not brand-new to this handoff MUST have a matching `carried_items:` frontmatter entry (schema: `coordinator/schemas/handoff.schema.json` `carried_items`), keyed on a stable `carry_id` that survives re-wording — never re-derive the count from prose, never key identity on the description text.

- **Minting `carried_items`.** A brand-new item mints a fresh `carry_id` (`cf-<slug>-<6hex>`). An item continuing from the predecessor keeps that `carry_id` byte-identical. That is the whole rule — identity threads through re-wording, and nothing counts the hops.
- **The disposition gate.** Before this handoff is written, run `python3 "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/handoff-carry-gate" check <this-handoff-path>` (falls through to the engine-resident `coordinator/bin/handoff-carry-gate` trampoline; see `coordinator_core/ops/handoff_carry_gate.py` for the pure logic). It REFUSES (exit 1) exactly three things: a missing or non-string `carry_id`, an unrecognized `disposition`, and a terminal disposition (`closed`/`spun_off`/`blocked`) with an empty `disposition_detail`. Exit 2 is an internal error. **Carry depth is not among them** — an item may be carried forward indefinitely, so long as each hop declares its state.
- **Sanctioned exits.** Set `disposition` to `closed` (with `disposition_detail` naming why — mirrors `deployment_state: closed`'s `closed_reason` vocabulary), `spun_off` (with `disposition_detail` naming the spinoff handoff), or `blocked` (the sanctioned exit for a genuine external/hardware dependency — e.g. Windows-host validation — with `disposition_detail` naming the concrete blocking condition, not a bare "blocked" restatement). All three are refused too if `disposition_detail` is empty — the terminal states are visible-and-explicit, not a rubber stamp.

---

## Supersession — Genuine Dead-End (case ii)

When a workstream is superseded and ownership moves to a named successor, the assembler's `d6` directive (`handoff.supersede_predecessor`, computed in `coordinator_core/baton_assemble/__init__.py`) fires automatically on the normal `/handoff` path whenever this brief's lineage names a predecessor — it stamps the predecessor `continued` + `continued_into:<successor>` and archives it, in the same transaction as the successor's own mint. For a predecessor cut before `d6` existed, or otherwise stranded off the normal path, the manual equivalent is the `supersede` verb (NOT `chain` — `chain` only ever dispatches `stamp_shipped` or `stamp_only`, never `continued`; see `handoff-archive-transition.py`'s own docstring):

invoked through the settings-home forwarder — `python3 "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/handoff-archive-transition" supersede <absolute-predecessor-path> --continued-into <successor> --exclude <successor>`. `--exclude` is required — without it the live-children guard sees the successor (which names the predecessor via its own `predecessor:` field) as a live child and the op silently retains rather than superseding.

The other shape — a **genuine dead-end with no continuation at all**, including the reconcile-to-terminal case where every next-step was closed by work that landed after the baton was written — now has a one-call op: `handoff.reconcile_close_terminal`, which composes the `closed` stamp and the archive move, is idempotent, and refuses on live children. **It is not yet reachable from a skill — no `bin/` forwarder exists for it** — so until one ships, express the close by hand-authoring `deployment_state: closed` + `closed_reason: <cancelled|displaced|stale>` (human/session-only — no automated writer stamps `closed`), or, for a content-free/never-used stub, remove it (git history is the trail). **Hand-authoring an audit record is not the close** — a reconcile narrated into a `*-baton-reconciled-closed.md` file without the frontmatter flip leaves the baton resurfacing as pickup-ready; stamp the frontmatter in the same breath as the record. Supersession is a PM-or-roadmap event, not an EM unilateral call on adjacent handoffs — do not park another session's handoff without an explicit successor link or a named dead-end reason.

**Roadmap batons are never an automated supersede target — a `d6` decline there is the doctrine working, not an engine bug.** A roadmap baton's dependents point at it through `blocked_by:` (a `stub_id:` edge), which no guard on the archival path can see, so stamping one `continued` and archiving it silently strands its dependents. Because superseding a roadmap baton is exactly the PM-or-roadmap event the paragraph above reserves, `d6` (`handoff.supersede_predecessor`) declines to arm when the resolved predecessor's `kind` canonicalizes to `roadmap-baton`, surfacing a judgment point instead of an armed directive. Read that decline as intended behaviour and route the supersession through the roadmap owner; do not file it as a defect, and do not reach for the manual `supersede` verb to route around it. Which baton states admit an automated supersede is settled, not open: **none**, and the refusal keys on canonical `kind` alone — a roadmap baton with no live dependents is refused identically, because the dependent set is authored incrementally (absent today, authored tomorrow) and a stub id outlives the baton file. Where a stranded baton's dependents must be freed, the sanctioned route is repointing their `blocked_by` at the successor that actually ships — session-decided and recorded, never swept.

**Closing one whose deliverable was a cross-repo memo? The named receiver is still waiting — send the stand-down notice before you stamp `closed`.** If the handoff's deliverable was a memo to a named receiver — today that means the DoE→`claude-klabauter` pair specifically, not a fleet-wide broadcast — hand-authoring `closed_reason` is not the finish line by itself: draft and send that receiver a stand-down notice via the settings-home forwarder — `${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/cross-repo-memo` — so they don't keep waiting on a workstream that already ended.

---

## Notes

- Each session writes a NEW file with a unique timestamp — never overwrite other sessions' handoffs.
- Keep it concise. Focus on state that MEMORY.md doesn't capture: in-progress work, blockers, uncommitted changes.
- If the PM provides arguments (e.g., `/handoff focus on auth refactor`), incorporate that context into `## In-Progress Work` and `## Recommended Next Steps`.
- **A Claude Code restart is a session boundary, not a step within a session.** If your workflow needs an MCP-bridge restart, a runtime artifact rebuild, or a `/reload-plugins` between code-edit and verification, run `/handoff` BEFORE the restart, not after.
- **Cross-repo communication is not a handoff use-case.** Route it via the PM as relay or `cross-repo-memo`.
- **Commit shape:** default scoped commit via `ceremony.scoped_git_commit` (claude-klabauter; `paths`, `message`) — it selects the agree-case vs. private-index form for you; never `git add -A`/`.`. → `docs/wiki/scoped-safety-commits.md § The trailing pathspec is a proxy for scope, valid only while index and worktree agree`.
- **Archiving is automatic, not something this skill does.** The boot sweep (`fleet.archive_completed_handoffs`) and `/update-docs` Phase 8 close the loop on a clean chain by dispatching `handoff.archive_transition` via `cc_invoke.route_mutation`. The same op is reachable directly (seam-absent fallback for the ordinary chain-archival path) through `python3 "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/handoff-archive-transition" chain "<predecessor-path>" --exclude "$HANDOFF_FILE"`. For a manual supersession park (a dead predecessor with a named successor), use the `supersede` verb per § Supersession — Genuine Dead-End above, never `chain`.
