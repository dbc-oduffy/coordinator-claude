---
name: handoff
description: "Mid-workstream save-state under context pressure — always a continuation."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session Handoff — Save State for Next Session

## Handoff Lineage

**Predecessor is the baton this session was born with.** A session that writes a CONTINUATION
always has one — the assembler resolves it, never the EM. Deflection kinds (`spinoff`,
`goal-seed`, `roadmap-seed`) carry `predecessor: none` by schema invariant
(`handoff.schema.json`'s `kind`/`predecessor` cross-field rule) — also not an EM inference; this
does not mean every handoff has a predecessor. Spinoffs are PM-authorized forks only, never
self-authored. Tripwire: `A-SESSION-IS-NEVER-STANDALONE`.

> **The baseline trigger is involuntary** — context pressure forcing a stop mid-workstream before
> the next action can land. Reaching for `/handoff` because the work *feels* like a good place to
> pause is the disqualifier. Workstreams end via `/workday-complete`, `/merge-to-main`, or
> `/quick-wrap`, never via handoff. **Four deliberate triggers also fire. 1 — the PM asks:** their
> ask IS the authority; no context-pressure test applies or is owed back. **2 — parking:** the next
> action is blocked outside this session's reach (a PM decision, a sibling repo, a peer's landing)
> for longer than this session, and the remit is *resume when the blocker clears*. **3 —
> plan→execute:** review-integration done and the plan is ready to execute. **4 —
> review-owed close** (§ Step 0), which still requires genuine context pressure.

> **Continuation vs. fork.** This skill writes a *continuation* — work this session was doing that
> someone resumes. A *different* mid-session topic for someone to pick up cold is `/spinoff`
> (`kind: spinoff`, `predecessor: none`). **The next phase of the same multi-phase workstream
> (research → goal-setting → plan → execute → verify) is a continuation**, even when the phase
> boundary reads as a new topic — never redirect it to `/spinoff`.

> **A `roadmap-baton`'s successor is a `roadmap-baton`** and inherits `stub_id`, `roadmap_id`,
> `blocks`, `blocked_by`, `sprint`, `wave`. The predecessor is superseded and archived in the same
> move — succession kills the originator, roadmap batons included. Both halves or neither:
> `blocked_by` resolves by `stub_id`, so inheriting without archiving duplicates a globally-unique id,
> and archiving without inheriting strands the dependent. Cutting a `session-handoff` successor from a
> baton silently drops that identity.
>
> **The archival half cannot currently run** (see § Supersession — `handoff.archive_transition` is
> suspended), so a roadmap-baton succession cannot satisfy "both halves" through any sanctioned
> route. Hand-stamp the predecessor `deployment_state: continued` with `continued_into:` BEFORE the
> successor carries `stub_id` forward — an inherited id beside a predecessor still advertising it is
> the duplicate-globally-unique-id failure above, and nothing warns.

The mechanical spine — deliverable/initiative id inheritance, frontmatter scaffolding,
`handoff_phase` stamping, tracker refresh, and (on a clean chain) predecessor archival — is
computed by `baton-assemble brief handoff <artifact-path>`, resolved per
`snippets/resolve-coordinator-bin.md` (Shape W on a PowerShell host). What follows is what it
cannot decide for you.

**`<artifact-path>` is the artifact this handoff is written FROM — on the plan→execute trigger that
is the PLAN, not a handoff.** Passing a handoff, or nothing, falls through silently to the
predecessor's id or a fresh mint; plan and executing handoff then carry different `deliverable_id`s,
and close-out reports a fully-shipped plan as entirely unshipped. Right on an ordinary
continuation; wrong and silent at the plan→execute seam.

**Divergent `deliverable_id`s are a judgment point, not a dead end.** `brief` surfaces
`j-divergent-deliverable-id` — `keep-plan`/`keep-predecessor`, `decision_note` required. Nothing
recommends a rung: the earliest artifact's id wins, and only you can see that history. Name the
survivor and how you know; the losing rung is excised before the cascade raises.

Feed resolutions back via `apply --decisions '<json>'`: a JSON object mapping each
`judgment_points[].id` to `{"disposition": "<value>"}`, values from that point's own
`dispositions[].value`. `{"value": "<v>"}` is equivalent; a `decision_note` sibling key carries
through.

**`apply` is the single route out — never hand-execute the directive list.**
`baton-assemble apply handoff <artifact-path> --decisions '<json>'`, resolved per
`snippets/resolve-coordinator-bin.md` (Shape W on PowerShell hosts) — same `<artifact-path>` as
`brief`.

Procedure detail — body authoring, `d5` release, next-steps durability,
`carried_items` minting and its disposition gate, dirty-tree case-(c) and safe-commit grouping,
supersession, orientation refresh — arrives with this invocation from
`coordinator/skills/handoff/residue/`; you should not need to open it.

---

## Step 0: Trigger Check — Is Context Pressure Actually Forcing This?

Confirm at least one trigger fires and no NO-test trips. The PRIMARY question: can this session
still take its next action? If it can *and nothing outside the session blocks it*, you are
deferring, not handing off — a violation regardless of how tidy the state looks. If nothing fires,
STOP and take the next action here.

**Two triggers skip this gate.** A PM ask is self-authorizing — write it, don't audit it against
context pressure and don't answer with a trigger analysis. A blocked next action is real too: name
the blocker and the event that clears it in the successor's remit.

**A parked successor's frontmatter is `deployment_state: awaiting_gate` plus a named gate —
`blocked_by` when a stub or handoff on the graph clears it, `blocking_notes` when nothing on the
graph does (a sibling plane's ruling) — with `pickup_ready` false or omitted.** The scaffold hands
you `ready_to_fire` + `pickup_ready: true`; leaving that above a body full of blocker prose births
the baton advertising itself as available work, and nothing warns. Authorization-pending is not a
gate — a PM handoff or `/pickup` is itself the authorization, so never author `awaiting_gate` for
that reason; a parked baton stays legal only when its blocker is something else — a sibling repo's
landing, a peer's dependency, a PM product decision.

**Inverted antipattern:** picking up a handoff does not license appending progress to the
predecessor's (now `status: claimed`) body instead of writing a successor. The pickup index treats
it as historical, so stapled-in progress is invisible to the next opener. About to edit a
`status: claimed` body to record what you just did? STOP and run this skill from the top.
