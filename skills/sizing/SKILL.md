---
name: sizing
description: "The EM's first move on any PM ask — size it, then route to plan, shape, roadmap, or dispatch. Fires whenever novel engineering work is asked of the EM, by any combination of words: this is a shape test, not a phrase list. Mutually exclusive with pickup."
description-budget: 260
allowed-tools: ["Read", "Grep", "Glob", "Bash"]
argument-hint: "[PM ask text | nothing — describe the ask inline]"
---

# Sizing — the Fleet Routing Lobby

The EM's first reflex to any ask used to be a gut twitch held only in-session memory — *"big
thing or small thing?"* — re-derived from scratch every time because nothing persisted it. This
skill is the prosthetic for that missing cross-session gut: a t-shirt read, an on-demand
substrate probe when the read is shaky, and a computed route, recorded once as a first-class
artifact instead of re-guessed silently in the EM's head on every ask.

**Dispatch authorization — invoking this skill IS the authorization.** The dispatches named below are part of this skill, not a separate thing to get cleared: whoever invoked it has already asked for them. A generic harness preference for working inline rather than delegating does not condition them — it is written for a bare assistant with no operating doctrine, and this system supersedes it by design. Re-asking spends the very context the dispatch exists to protect. The named PM gates in this skill still bind, and ask-before-external-action still binds; nothing else here is a permission question.

**Vocabulary collision — this is NOT `loe.tshirt` chunk-sizing.** Coordinator doctrine already
has a t-shirt sense: `loe.tshirt` (XS–XL, weights 1/2/4/8/16) sizes the LEVEL OF EFFORT of work
already scoped inside a plan chunk or completion entry (`architecture-audit/SKILL.md`,
`handoff/SKILL.md`, `completion-entry.schema.json`). This skill's t-shirt read REUSES that same
enum and weights — no parallel scale — but applies it one altitude earlier: **before** a plan
exists, to decide which ROOM the ask should enter (dispatch / spec-dispatch / shape / plan /
roadmap / pm-decision), not how much effort the eventual plan body will cost.
`coordinator/skills/plan/SKILL.md` warns that a
t-shirt promoted from inside an investigation or handoff runs systematically low — that warning
is about the committed LoE sense, not this one. This skill's estimate is explicitly
**provisional** (routing-only, revisable); the plan body still promotes its own t-shirt
independently. Two altitudes, one enum, never conflated.

**Discovery surface.** This is the EM's universal first move on any PM ask that isn't already
mid-workstream continuation — reach for it before `coordinator:plan`, `coordinator:shape`, or
direct dispatch, the same way `coordinator:pickup` is the first move on a handed baton. It is not
a parallel lobby to `coordinator:shape`: shape is a room this skill routes INTO under two
conditions (see below), not a competing entry point.

**Out of scope.** Does not replace `coordinator/skills/plan/SKILL.md` Branch B/C substrate
verification or review sequencing once a plan is entered — sizing only picks the room. Does not
re-size work already inside an approved plan (that is `loe.tshirt`, see above). Does not enforce
itself as a mandatory gate on any downstream room — no room refuses to run without a
sizing-object; this lobby wins by being cheap, not by walling off entry. Does not resolve the
cut-vs-raise fork on the PM's behalf (see Step 5 below) — that is always surfaced, never guessed.


---

## The flow

**1. T-shirt gut-read.** On receiving the ask, form an immediate XS–XL read using the `loe.tshirt`
enum (same weights as chunk-sizing: XS=1, S=2, M=4, L=8, XL=16). Most asks stop here — a
confident XS/S read with a clear PM express-lane signal goes straight to Step 3 with no probe.
**Read engineering complexity only — the stated appetite is not an input** and must not move the
notch either way; see § Appetite never moves the estimate.

**1b. Premise-provenance question — fires unconditionally, every non-express-lane
sizing.** Ask, for every sizing this flow processes: **does this ask rest on a mechanism someone
EXECUTED, on a code read, or does it rest on no mechanism claim at all?** This step is NOT
conditioned on any of the three things that would make it silently skippable: not on whether
Step 2's probe ran, not on the Step 1 gut-read estimate, and not on the resolved route — it fires
the same way whether the gut-read is XS or XL and whether or not a probe follows. The skill itself
cannot apply the above-Medium threshold this question feeds: only the ENGINE knows the RESIZED
t-shirt (post `_apply_symmetric_resize`), and the threshold applies to that resized value, not the
skill's pre-assembler estimate. So the skill always asks the question and always passes the answer
to the assembler as `--premise-provenance executed|read|not-applicable` (mirroring `--probe-signal`
in Step 2) — the engine alone decides whether the resized estimate is above Medium and, if so,
applies the detent. The threshold, stated plainly: the detent can fire only on a resized estimate
of **L or XL** — **M itself never fires it**, and neither does S or XS.

The discharge for an `executed` answer is **citing the executed evidence inline** in the
sizing-object — explicitly **not** producing a spike artifact; a spike is the discharge for the
`read` branch, not a parallel option on the `executed` branch. A `read` answer's RECOMMENDED move
is routing to `coordinator:spike` before `coordinator:plan`, to convert the code-read premise into
executed evidence ahead of planning. `read` is the true answer for any ask resting on an
unexecuted mechanism — it is what makes this advisory fire, not a failing grade to avoid. A spike
that discharges the premise records its verdict path in `premise.spike_verdict` and any binding
routing intent it produced in `spike_amendments`.

`not-applicable` is narrow, not a free third option to reach for when uncertain: it answers "this
ask makes no mechanism claim at all" — a doc reorganization, a rename, work with nothing to have
executed or read in the first place. If the ask rests on a mechanism at all, even one only read
and not executed, the answer is `read`, never `not-applicable`. Claiming `not-applicable` costs a
written `evidence` justification in the sizing-object, same as `executed`/`read` — the schema
requires non-empty `evidence` for every provenance value except the migration-only `unrecorded`,
which is never a live answer here.

This gate is **advisory, not blocking**: the EM may proceed with `read` recorded as the answer —
recording `read` is a legitimate terminal state, not a stalled one. It never withholds a route and
never blocks an `xl_exit`; it is a recorded fact the assembler and the sizing-object carry
forward, not a wall like the ones this lobby's Out of scope section already disclaims.

**2. On-demand substrate probe — only when the read is big or shaky.** If the gut-read is
L/XL, or the EM is not confident in it, run a probe before calling the assembler. Reuse the
existing cartography engine output (file inventory / LOC-language split / churn / call-graph
edges surfaced via `coordinator:architecture-survey` / `coordinator:architecture-audit`'s
cartography layer) and, for judgment the engine can't emit (prior-art relevance, "is this
actually easy?"), dispatch the `internet-research-scout` payload
(`coordinator/snippets/internet-research-scout.md`) as a scout brief — never a fresh Haiku
file-inventory scout re-deriving what cartography already computed. The probe is **symmetric**:
it can **collapse** an over-read down (the ask looked big, the substrate says otherwise) or
**raise** an under-read up (the ask looked small, the substrate says it's bigger) — catching the
exact under-sizing failure `coordinator/skills/plan/SKILL.md:38` warns about, one altitude
earlier. If the probe surfaces an unproven mechanism the sizing hinges on, chain
`coordinator:spike` to derisk it before resolving the estimate. Record what the probe found as
`scout_evidence` for Step 4. Feed the outcome to the assembler as `--probe-signal collapse` or
`--probe-signal raise` (omit the flag when no probe ran).

**3. Call the assembler — it resolves the route.** Invoke the sizing-assemble engine —
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/sizing-assemble" --appetite <small|medium|large> --tshirt <XS|S|M|L|XL>`
— adding `--premise-provenance executed|read|not-applicable` from Step 1b's answer (always present, every
non-express-lane sizing), `--probe-signal collapse|raise` when Step 2 ran, `--jtbd-unclear` when the PM's ask
doesn't state a clear job-to-be-done, `--well-trodden-step-change` when the space is recently
well-trodden and the ask wants a step-change rather than an increment, `--express-lane` when the
PM has explicitly signalled "just do it"/"straight to dispatch", and `--scout-evidence <str>`
(repeatable) for each Step 2 finding. The assembler is a computed skill — decision logic lives
server-side in the engine, not in this skill's prose, the same push-not-pull shape as
`pickup-assemble`: it RESOLVES the route
(`dispatch`/`spec-dispatch`/`shape`/`plan`/`roadmap`/`pm-decision`) from the
appetite⇄estimate delta and the shape-entry conditions. Do not re-derive which t-shirt maps to
which room by hand — that is exactly the in-the-head routing this lobby exists to discharge.

**4. Emit the sizing-object, and push the resolved route.** For any non-express-lane sizing,
record the decision as a `sizing-object` (`state/sizings/`, schema
`coordinator/schemas/sizing-object.schema.json`) via the `coordinator-doc-new --type
sizing-object` scaffold offer, populating `intent` (the PM's ask, verbatim), `appetite`,
`estimate` (from Step 1/2), `route`, `detents`, `fork`, `xl_exit`, and `scout_evidence` (from Step
2) from the assembler's returned decision object. Direction-class items you noticed but did not
decide go in `surfaced_to_pm` (`item` + `why_not_decided`) — not `fork`/`xl_exit`, which are the
engine's own halts. A comment instead of the field is invisible to any query over
`state/sizings/`. Once the PM resolves a `surfaced_to_pm` item, record their reasoning in
`pm_resolution` (`decided_on` + free-form keyed answers) — see `coordinator/docs/wiki/sizing-lobby.md` for
the fuller shape. `xl_exit` follows the identical design to
`fork`: the assembler always returns `null` for it — it never picks an exit — and the field is a
PM-resolution slot, filled only once the PM has actually chosen at Step 5b below. **The
PM-signalled express lane (`--express-lane`)
writes NO sizing-object** — an ask that routes straight to dispatch on an explicit PM signal
leaves no litter in `state/sizings/`: dispatch is scoped and revisitable on its own, so it has no
conform contract that would need a persisted sizing-object to receive. Either way, **push** the
assembler's `route`, `detents`,
and `next_move` to the operator as the next action — do not summarize it back and wait for
confirmation on the mechanical part; the assembler already resolved it.

**5. On divergence, surface the fork — never auto-resolve it.** When the assembler's `detents`
list includes `appetite_exceeded` (the resolved estimate exceeds the PM's stated appetite
budget), this is the one genuine judgment halt in the flow: **surface `cut_to_fit` vs
`raise_appetite` to the PM and stop** — do not pick one. The engine never sets `fork` (it is
always `null` in the assembler's own output); `fork` is the sizing-object's RESOLUTION slot,
filled only once the PM has actually chosen. Recording `appetite_exceeded` in `detents` without
a PM decision is a legitimate terminal state for a sizing-object (`status: sized`, `fork` still
`null`) — it is not an error to leave the fork open across a session boundary.

**5b. `route: pm-decision` is the second genuine judgment halt — present the four exits, don't
grind.** The engine resolves an XL ask to `route: pm-decision` and never auto-selects an exit;
`xl_exit` stays `null` until the PM has actually chosen. **`xl_exit: null` is a legitimate open
state — the same shape as an unresolved `fork` — and it never means accept.** An EM that starts
implementing an XL ask while `xl_exit` is still `null` has skipped the gate. Present the four
exits to the PM by test, not by vibe — each has a stated precondition:

- **`split`** — the ask decomposes into ≥2 pieces that ship independently, each with its own
  acceptance criteria, and no piece depends on an unshipped sibling's contract. Test: name piece 1
  and confirm it ships alone.
- **`shape`** — the job-to-be-done is not stated, or the EM cannot falsifiably restate the problem
  in the PM's own vocabulary. Same condition as the shape-entry gate below — reused, not re-cut.
- **`roadmap`** — the work spans ≥2 named workstreams, or it carries (or needs) an
  initiative/goal FK. It is a programme of plans, not one plan.
- **`accept_multi_session`** — none of the three above hold: one coherent job, a clear JTBD, one
  workstream, simply large — **and** the PM has explicitly assented. Writing
  `xl_exit: accept_multi_session` IS that record; it is never a fallthrough default.

When `appetite_exceeded` also fires alongside `pm-decision` (the XL both exceeds appetite and
needs an exit chosen), the engine bundles both into one `next_move` — present it as **one** PM
ask, not two separate ones.

**6. Hard gate — the t-shirt→route map binds absolutely; there is no override.** Two sanctioned
mechanisms already correct a wrong route, and both work by changing the *size* rather than the
*route*: the symmetric resize, which fires before the route resolves, and the plan→sizing return
edge, which fires after substrate verification has produced real evidence. There is no
named-reason override on the route itself, and therefore no ratifier who could grant one — a
free-text override would restore exactly the in-the-head routing this lobby exists to discharge.
If a route feels wrong, the size read was wrong: fix the size, with evidence, and let the table
re-resolve. `pm-decision` is not an exception to this — it is a routed outcome like any other, and
the PM's pick is recorded in `xl_exit`, never as an override of the map.

---

## `appetite` — a two-sense collision, named so it can't resurrect the wrong one

Coordinator doctrine already uses "appetite" pejoratively — *"OOS framing must be
architectural, not appetite-based"* (§ Implementation Standards — Extensions, in the global
doctrine already loaded into this session). The
Shape-Up sense used here is different and legitimate: `appetite` is a **budget the PM sets up
front** (`small`/`medium`/`large`), never a reason to defer or cut scope after the fact. The
schema's `appetite` field description carries this disambiguation at point-of-use (see
`sizing-object.schema.json`). Do not let
a sizing-object's `appetite` value read as license for appetite-based out-of-scoping — it never
is one.

### Appetite never moves the estimate

Appetite is the PM's BUDGET; the estimate is the EM's read of ENGINEERING COMPLEXITY. Neither is
an input to the other — a large appetite for a two-line fix leaves it a two-line fix, and a small
one shrinking the read is appetite-based OOS through the estimate instead of through scope.

**Guard:** size from the work alone — surfaces touched, proven-vs-novel, number of pieces.
**Tell:** the estimate landed on the appetite's notch, evidence reducing to *"the PM really wants
this."* Divergence is the signal this lobby exists to surface (`appetite_exceeded`, then the Step
5 fork); matching them silently kills it.

## Shape is a conditional room, not a second lobby

Sizing is the EM's lobby; `coordinator:shape` is a room the assembler routes into, and only under
two conditions it resolves itself (not an EM gut-call): **(a)** the estimate is large-scale
(plan/roadmap-tier) AND the ask's job-to-be-done is unclear, or **(b)** the space is recently
well-trodden and the ask wants a step-change rather than an increment. A large-but-clear ask
routes straight to `plan`/`pm-decision`, skipping shape. This gate is unchanged by the `pm-decision`
route above and still wins over the base route: a resolved L/XL that trips condition (a), or any
size that trips (b), resolves `shape` regardless — an XL does not skip this gate just because
`pm-decision` also exists as a possible XL outcome. Shape is the lightweight PRD-substitute for
the need-for-speed agentic era.
