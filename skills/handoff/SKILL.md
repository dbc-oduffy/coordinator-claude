---
name: handoff
description: Mid-workstream save-state under context pressure; a continuation.
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session Handoff — Save State for Next Session

## Handoff Lineage

**Predecessor is the baton this session was born with.** A CONTINUATION always has one; the
assembler resolves it, never the EM. Deflection kinds (`spinoff`, `goal-seed`, `roadmap-seed`)
carry `predecessor: none` by schema invariant. Spinoffs are PM-authorized forks only.

> **The baseline trigger is involuntary** — context pressure forcing a stop mid-workstream before
> the next action can land. Reaching for `/handoff` because the work *feels* like a good place to
> pause is the disqualifier. Workstreams end via `/workday-complete`, `/merging-to-main`, or
> `/quick-wrap`, never via handoff. **Four deliberate triggers also fire. 1 — the PM asks:** their
> ask IS the authority; no context-pressure test is owed. **2 — parking:** the next
> action is blocked outside this session's reach (a PM decision, a sibling repo, a peer's landing)
> for longer than this session. **3 — plan→execute:** review-integration done and the plan is ready to execute. **4 —
> review-owed close** (§ Step 0): the owed review is un-runnable in this session for a reason on
> the closed class of un-runnable-here reasons, cited by name.

> **Continuation vs. fork.** This skill writes a *continuation*. A *different* mid-session topic
> for someone to pick up cold is `/spinoff`. The next phase of the same multi-phase workstream is a continuation, never a `/spinoff`.

> **A `roadmap-baton`'s successor is a `roadmap-baton`** and inherits `stub_id`, `roadmap_id`,
> `blocks`, `blocked_by`, `sprint`, `wave`; the predecessor is superseded and archived in the same
> move; both halves or neither (`blocked_by` resolves by `stub_id`). Archival runs via
> `d6`'s supersession route (§ Supersession) — `mode='supersede'` needs `--continued-into` naming
> the successor; never hand-stamp `deployment_state: continued`.

`baton-assemble brief handoff` fires at entry and computes the mechanical spine (id inheritance,
frontmatter, `handoff_phase`, tracker refresh, predecessor archival). The brief, its open
decisions, the decisions-file template and the literal `apply` line arrive with this invocation.
Write your answers into the template at the named path and run the rendered line with `--title "<one line>"` appended, from the invocation argument (or the handoff's own subject) — `apply` refuses a missing, blank or placeholder title. An unanswered `<CHOOSE: …>` or `<NOTE: …>` placeholder makes
the file unparseable, and `apply` refuses it.

**The brief names the rung the lineage resolved from.** If it is not the artifact this handoff is
written from, that is the mis-link (on plan→execute the source is the PLAN). Stop and
resolve before running `apply`. Divergent `deliverable_id`s: the earliest artifact's id wins; name the survivor.

**`apply` is the single route out — never hand-execute the directive list.** `apply` cannot run? Repair `PATH` and retry; still blocked → leave the draft at its target path and name it in the final report.

No brief block in context means the entry hook failed open: run `baton-assemble brief handoff`
with no artifact-path, resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`.

Once `apply`'s commit lands, trigger project-rag's SCIP rebuild in the background (best-effort,
never blocks): `"$_py" "${CLAUDE_PLUGIN_ROOT:-<content-root>/coordinator}/bin/scip-rebuild-at-ceremony.py" --ceremony handoff`.
Then refresh and republish the structural index if drifted:
`"$_py" "${CLAUDE_PLUGIN_ROOT:-<content-root>/coordinator}/bin/structural-index-refresh.py" --root <repo-root> --timeout 0`
(`resolve-coordinator-bin.md`).

Procedure detail arrives with this invocation from `coordinator/skills/handoff/residue/`. Background (optional): `coordinator/docs/wiki/skills-corpus/handoff-residue.md`.

**`d5` releases the plan artifact-claim only; the path-touch plane is a separate close-time
check.** Before this session ends, run `session-claim-cli list-claims-by-session <sid>` and
release each `path\t<p>` line it does not need with `session-claim-cli release-artifact artifact
<path>`. Recheck any path a safe-commit already committed but this session then edited again.

---

## Step 0: Trigger Check — Is Context Pressure Actually Forcing This?

Confirm at least one trigger fires and no NO-test trips. The PRIMARY question: can this session
still take its next action? If it can *and nothing outside the session blocks it*, you are
deferring, not handing off — a violation regardless of how tidy the state looks. If nothing fires,
STOP and take the next action here.

**Two triggers skip this gate.** A PM ask is self-authorizing — write it, don't audit it. A blocked next action is real too: name
the blocker and the event that clears it in the successor's remit.

**On a box whose successor cannot be reached (a cloud session), context pressure is not a handoff
trigger at all.** Append what the post-compaction self needs to the baton this session already has
(`baton.carry_forward`; the advisory names the path), and continue the run. A PM ask and a blocked
next action still qualify anywhere.

**Trigger 4 (review-owed close) is an instance of this same blocked-next-action skip, not a
second discharge.** The closed class of un-runnable-here reasons is stated at
`coordinator/docs/wiki/coordinator-tripwires/two-ceremonies-two-predicates-one-handover.md`. Trigger 4 qualifies only when the
owed review is un-runnable in this session for a reason on that class — a hard-stop oracle
disagreement, a quota-exhausted dispatch, a live peer's files this session must not touch, or the `review_scale`
gate returning unresolved on the row-4 brightline inputs where the per-owned-commit summation
is itself un-runnable here for a separately named external reason (not merely un-performed) — each with its clearing event outside
this session's reach. Name the blocker and that event in the successor's remit; no reason off the class by analogy.
**A successor session existing is not itself a qualifying clearing event:** the clearing event is
the outside-the-session fact (PM/reviewer-pool decision, quota reset, peer's landing) that
lets the review run. `/handoff` itself reviews nothing (`residue/065-does-not-review.md`); the successor runs the owed review at its own close.

**A parked successor's frontmatter is `deployment_state: awaiting_gate` plus a named gate —
`blocked_by` when a stub or handoff on the graph clears it, `gate_notes` when nothing on the
graph does — with `pickup_ready` false or omitted** (the scaffold hands you `ready_to_fire` + `pickup_ready: true`). A gate a human clears carries a `gate_evidence` leg of kind `human` with its
reason; where a check shows whether the condition fired, add a `probe-command` leg (repo key,
script plus args, what the output reads) — or, while the authoring verb rejects it, name the same three in `gate_notes`. Never author the clearer class. Authorization-pending is not a
gate; a parked baton stays legal only
when its blocker is a sibling repo's landing, a peer's dependency, or a PM product decision.

**Never append progress to a `status: claimed` predecessor body instead of
writing a successor.** About to? STOP and run this skill from the top.
