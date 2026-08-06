# Sizing — the fleet routing lobby


Purpose: this is the doctrine home for the `sizing` skill and the `sizing-object` artifact —
why they exist, the vocabulary collisions their design had to reconcile, and how sizing relates
to the pre-planning triage it sits in front of. Read this before touching
`coordinator/skills/sizing/SKILL.md` or `coordinator/schemas/sizing-object.schema.json`.

## What shipped in the core build

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-021 -->
The buildable core landed as one unit, not a staged rollout: a first-class `sizing-object`
schema (reusing `loe.tshirt`, § below), doc-type registration plus the scaffolder tooling, the
`sizing` skill body, and the engine-resident `sizing_assemble.route()` hot-path assembler that
resolves the routing table (§ The route table, below). Together these are what makes sizing the
EM's computed first move on any PM ask, rather than a doctrine statement with no artifact behind
it — the discharge-test instance named in § Why it must be ritualized.

## Why it must be ritualized — the amnesia prosthetic

A meatspace EM's first reflex to any incoming ask is a gut twitch — *"big thing or small
thing?"* — and a human carries that intuition **across time**: yesterday's estimates calibrate
today's. A Claude EM does not get that continuity. Every session is Sisko unstuck in time in
"The Visitor" — it lands with the gut wiped, no accumulated "yeah, that's doable" or "you've got
to be kidding," and would otherwise have to re-derive sizing judgment from nothing, silently, in
its own head, every single session.

Sizing is the **prosthetic for that missing cross-session gut**. It reconstitutes the intuition
an amnesiac EM cannot hold between sessions from three durable inputs instead: disk state (what
already exists), a t-shirt gut-read (the cheap first pass), and — only when the gut-read says
"big" or "uncertain" — an on-demand substrate probe. None of those three requires the EM to
remember anything from a prior session; the reconstitution happens fresh, every time, from
artifacts that outlive the session that wrote them.

This is also the concrete, worked instance of coordinator's own **discharge test** — *"for every
rule: what artifact discharges it? If the answer is 'the operator remembers,' the work is not
finished."* The rule being discharged is *"size the ask before you route it"* — previously a fact
the EM had to remember to apply, session after session, from a routing heuristic that lived only
in its own head (`coordinator/skills/plan/SKILL.md` Branch A, see § Relationship to Branch A
below). Sizing converts that remembered rule into a computed decision surface: a sizing-object on
disk plus an engine-resolved route, not a fact an EM must recall to apply correctly.

## The adventure-chooser reuse

Sizing does not invent a new routing pattern — it is another instance of the **computed skill /
assembler** shape already load-bearing elsewhere in coordinator (`pickup_assemble.brief()` is the
sibling precedent). The route from an ask to a room (express lane / plan / shape / roadmap) is
resolved by an engine-resident `sizing_assemble.route()` compute layer, not chosen by prose
inside the skill body — a routing TABLE living in a SKILL.md is exactly the "deterministic
if/else in a markdown fence at the logic level" defect the computed-skill contract forbids
(assemble and push; never store-and-make-them-pull).

The unit of extraction here is the mechanical *step*, not the mechanical *branch* — the principle
that licenses pulling the routing table out of the skill body entirely rather than merely
refactoring it in place. `coordinator/skills/sizing/SKILL.md` is, per this reuse, reduced to the
irreducible non-branching action core plus the one genuine judgment halt the engine cannot resolve
(the cut-vs-raise fork, below) plus the push of the engine-resolved route to the operator. It
carries no branch-selection prose — that is the routing table's job, and the routing table lives
in the engine, not the skill.

## The three D1 vocabulary reconciliations

Three terms sizing needed already carried meaning elsewhere in coordinator doctrine. Each
collision is a correctness item, not a naming nit — an operator who reads the sizing sense as
the pre-existing sense will misapply doctrine.

### 1. Appetite has two senses — do not conflate them

Coordinator doctrine already uses "appetite" pejoratively — global `CLAUDE.md`'s Implementation
Standards extensions state: *"OOS framing must be architectural, not appetite-based."* That is
**appetite-based OOS** — a banned defer-reason, a smell that means someone decided not to do
something because they didn't feel like it, dressed up as scope discipline.

The sizing object's `appetite` field is a **different, Shape-Up sense**: appetite as a *budget
the PM sets* — a legitimate, deliberate input to the routing decision, not a reason to defer
anything. The field keeps the name `appetite` (the PM's deliberate Shape-Up term) rather than
being renamed to something duller and collision-free, because the Shape-Up framing is the point:
a PM stating "this is worth a day, not a week" is providing real information the estimate then
reconciles against.

**The guard against conflation is carried at point-of-use, not only here.** A wiki entry is
prose a reader consults if they think to; per the discharge test, the disambiguation that
actually matters is inline in the schema field's own `description` (read at authoring/scaffold
time, unavoidably, by construction). This wiki page is the *why* the schema-level guard exists —
read it to understand the collision, not as the mechanism that prevents it.

### 2. `loe.tshirt` reuse — no parallel scale

`loe.tshirt` already exists: XS/S/M/L/XL with weights XS=1, S=2, M=4, L=8, XL=16, consumed by
`architecture-audit/SKILL.md`, `handoff/SKILL.md`, and `completion-entry.schema.json`. The
sizing-object's estimate field **reuses this exact enum and these exact weights** — it is not a
new, sizing-specific scale that happens to look similar. One t-shirt vocabulary, one place its
weights are defined, every consumer (sizing included) points at it.

### 3. Routing estimate vs. committed LoE — the two-altitude model

`coordinator/skills/plan/SKILL.md` warns: *"handoff t-shirt sizing from inside an investigation
is systematically too low… T-shirt promotes from inside the plan body, not from the handoff."*
The sizing lobby estimates **before** planning even starts, which reads as a direct contradiction
of that warning until the altitudes are separated.

They are not the same estimate. The lobby's size is a **coarse, revisable ROUTING estimate** —
it answers "which room does this ask belong in?" (express lane / plan / shape / roadmap), and it
is explicitly marked `provisional` on the sizing-object. The plan body, once an ask actually
enters the plan room, still promotes its **own** committed t-shirt through its own normal
process — that estimate is the one `plan/SKILL.md`'s warning is protecting, and sizing does not
touch it. Two altitudes, two purposes: a fast coarse read that decides where to go, and a slower
committed read that decides what ships. Reading the lobby's estimate as if it were the
plan-body's committed figure is the mistake this reconciliation exists to prevent.

## Sizing routes; shape is a conditional room, not a rival lobby

The EM's first move on any incoming ask is **sizing** — always, unconditionally. **Shape** is not
a competing entry point but a room sizing routes *into*, and only under one of two conditions,
both resolved by the engine (`sizing_assemble.route()`), never left as an EM gut-call:

- **(a)** the size is large (plan/roadmap-scale) **and** the JTBD is unclear from the PM's ask, or
- **(b)** the problem/solution space is recently well-trodden and the ask wants a step-change,
  not another increment.

A large-but-clear ask **skips** shape entirely and routes straight to plan/roadmap — size alone
never triggers shape. The frame for why shape exists at all: it is the **lightweight
PRD-substitute for the need-for-speed agentic era** — a PM in this operating model won't author a
full PRD ahead of a day of launch-and-iterate work, so shape buys EM↔PM problem-alignment only in
the two cases above where size or well-trodden-ground actually earns the ceremony.

Encoding these two conditions in the engine rather than in EM judgment matters for the same
reason the routing table itself moved out of the skill body: if the shape-or-not decision were
left as an EM gut-call, routing-in-the-head — the exact failure mode sizing exists to discharge —
would sneak back in at one remove, just for the shape decision instead of the top-level one.

## The route table — six values, and the t-shirt→route mapping

`ROUTE_ENUM = ("dispatch", "spec-dispatch", "shape", "plan", "roadmap", "pm-decision")`.

| t-shirt | route | meaning |
|---|---|---|
| XS | `dispatch` | just dispatch; no artifact |
| S | `spec-dispatch` | light plan artifact, then dispatch; no Opus plan review |
| M | `plan` | full plan; auto-chains `coordinator:review` |
| L | `plan` | full plan; auto-chains `coordinator:review` |
| XL | `pm-decision` | not a room — surface four exits to the PM (§ below) |

`roadmap` stays in the enum even though it is no longer a *base* route for any single t-shirt: it
remains one of the four exits the PM can select at `pm-decision`, and a sizing-object records it
there via `xl_exit`, not via `route`.

The § Shape-is-a-conditional-room D5 gate above is unaffected by this table and still wins over
it: a resolved L/XL with an unclear job-to-be-done, or any size wanting a step-change in
well-trodden ground, resolves `shape` regardless of what this table alone would say.

### The appetite⇄estimate fork — surfaced, never auto-resolved

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-022 -->
The engine sizes **symmetrically**: it collapses an over-read t-shirt down and raises an
under-read one, in either direction, rather than only ever correcting downward. When the PM's
stated `appetite` and the engine's resolved estimate diverge, the engine surfaces that divergence
via the `appetite_exceeded` detent and stops there — it does **not** pick a resolution on the
PM's behalf. `fork` (the cut-vs-raise choice named in § The adventure-chooser reuse above) is the
sizing-object field that records which way the divergence was resolved, and the engine always
emits it `null`; only the `sizing` skill fills `fork`, and only once the PM has actually chosen.

This is a corrected defect, not the original design: code review caught the engine jamming
`fork=cut_to_fit` in as a placeholder value rather than leaving it unresolved, which would have
silently pre-empted the PM's choice on every divergent estimate. The fix routes divergence
through the `appetite_exceeded` detent instead, matching the same never-auto-resolve shape
`xl_exit` uses (§ `pm-decision` above) — a detent is advisory and queryable, never a decision the
engine makes quietly on its own.

## `spec-dispatch` — what it is, and why it reuses the plan artifact

**Artifact: the existing plan artifact, with `scope_mode: spec-dispatch`.** No new document
class, no parallel schema. `plan.schema.json`'s `scope_mode` is already a free-form string with no
enum, so admitting this value costs a description touch-up, not a schema migration.

**Why reuse rather than mint a lighter document class:** a parallel schema for a "light plan"
splits maintenance in two — every future plan-schema change becomes two changes, one per class,
kept in sync by discipline rather than by construction. Reusing the plan artifact with a
`scope_mode` discriminator means the S lane's document *is* a plan, just one whose Exit terminal
takes the light branch (see `coordinator/skills/plan/SKILL.md` § Branch A / Exit terminal); the
schema, the scaffold tooling, and every consumer that already knows how to read a plan keep
working unmodified.

**The S lane OWES**, in full:
- Branch B substrate verification, in full. This is precisely what makes skipping the plan review
  defensible — the lane is lighter because the substrate is verified, not because the bar is
  lower.
- Branch B.0's doubt-check at `production-patch` proportionality: one restating sentence, not the
  forced-articulation triad.
- The concurrent-session pre-flight (Branch B).
- The cross-plan conflict scan (Branch C). Cheap, and it is the thing that catches two EMs
  planning the same work.
- Both `scaffold-plan` invocation points — scaffold, and the write-time commit. A spec that exists
  but is untracked nearly escapes the audit trail.

**The S lane SKIPS:**
- Branch C's four-lens body composition. An S-lane body is four parts instead: problem sentence,
  file scope, acceptance criteria, test surface.
- The Opus plan review at Exit. The honest trade is the one `plan` already articulates for its own
  skip-review case: implement, and let `code-reviewer` catch the diff.

**The S lane NEVER skips** scoped-commit discipline, the pre-execute authorization gate, or
ask-before-external-action. A lighter lane means less ceremony, never fewer safeguards.

## `pm-decision` — the XL exits, and why there are exactly four

XL does not resolve into a room the way every other t-shirt does. The engine resolves
`route: pm-decision` and sets the `pm_decision_pending` detent; it never picks an exit. The PM's
choice is recorded in a sizing-object field, `xl_exit` — the exact same design as `fork`: the
engine always emits `null`, and the field is filled only once the PM has actually chosen.

`xl_exit` enum: `split` | `shape` | `roadmap` | `accept_multi_session`, or `null`.

Each exit carries a stated precondition, so the choice is made by test rather than by vibe:

| exit | precondition |
|---|---|
| `split` | the ask decomposes into ≥2 pieces that ship independently — each has its own acceptance criteria, and no piece depends on an unshipped sibling's contract. Test: name piece 1 and confirm it ships alone. |
| `shape` | the job-to-be-done is not stated, or the EM cannot falsifiably restate the problem in the PM's vocabulary. Same condition as the D5 shape-entry gate above — reused, not re-cut. |
| `roadmap` | the work spans ≥2 named workstreams, or it carries (or needs) an initiative/goal FK. It is a programme of plans, not one plan. |
| `accept_multi_session` | none of the three above hold — one coherent job, clear JTBD, one workstream, simply large — **and** the PM has explicitly assented. Writing `xl_exit: accept_multi_session` IS that record. |

**Anti-fallthrough — why `accept_multi_session` is defined by negation plus assent, not by
default.** `xl_exit: null` on a `route: pm-decision` object is a legitimate open state, exactly
like an unresolved `fork` — it means the PM has not chosen yet, and it never means accept. The
reason `accept_multi_session` requires both "none of the other three hold" *and* an explicit PM
assent, rather than either alone, is that "we knew this was multi-session and accepted it" and "we
failed to notice this was multi-session" produce identical-looking plans and very different
outcomes. A silent default to `accept_multi_session` would erase that distinction — an EM grinding
through an unrouted XL would look, on disk, exactly like a PM who deliberately chose to accept the
size. Requiring the assent is what keeps those two histories distinguishable.

## `surfaced_to_pm` and `pm_resolution` — the undecided and decided halves

Two sizing-object fields exist purely to give PM-owned material a queryable home instead of a
YAML comment or an ad-hoc key. `surfaced_to_pm` holds direction-class items the EM noticed but
deliberately did NOT decide while sizing (a standing ruling new evidence bears on, a
product-direction question, an irreversible/external action) — each entry stays listed until it
is resolved in its own artifact, never by editing the sizing-object in place. `pm_resolution` is
the counterpart: once the PM actually decides, their reasoning lands there, keyed by what it
resolved (`decided_on` plus free-form keys like `appetite_fork`, `xl_exit`, `wiki_home`). It is
reasoning only — `fork` and `xl_exit` stay the authoritative machine-readable record of those two
choices, and a `pm_resolution` entry must never contradict them.

## `premise` — where the estimate's foundation actually came from

Every sizing-object carries a required top-level `premise` object: `provenance` (a closed
four-value enum) and `evidence` (a string, required and non-empty for every provenance value
EXCEPT `unrecorded`). Where `appetite` (§ above) asks "how much is this worth," `premise` asks a
different, prior question: *what is the estimate actually resting on* — something someone ran, or
something someone read? An estimate can be well-calibrated in t-shirt terms and still rest on an
unverified guess about what the mechanism does; `premise` is the field that makes that distinction
queryable instead of silent.

**The four provenance values:**

- **`executed`** — someone actually ran the mechanism the ask depends on, and `evidence` cites
  what ran and what it showed. This is the strong case: the estimate rests on an observed result,
  not an inference.
- **`read`** — the premise rests on a code read, not an execution. **This is NOT a failing
  grade** — it is simply the true answer, and naming it truthfully is exactly what makes the
  advisory below able to fire. Marking `read` as `executed` to avoid the advisory would defeat the
  field's entire purpose.
- **`not-applicable`** — the ask makes no mechanism claim at all: a doc reorganization, a rename,
  anything with no runtime behavior to have gotten wrong. **This is not a default escape hatch.**
  An ask that DOES make a mechanism claim but wasn't executed is `read`, never `not-applicable`
  dressed up to dodge the honest answer.
- **`unrecorded`** — **migration-only.** The record predates this field, and there is nothing to
  retroactively cite. This value is never a valid answer for a record created after the field
  landed; a test enforces that no post-bump record carries it.

**The discharge rule.** `evidence` must cite the executed evidence **inline**, in the field
itself — not by reference to some other artifact the reader has to go find. Producing a
spike-result record is *one* valid way to generate that evidence, never *the* required
discharge mechanism; citing a prior test run, a REPL session, or any other concretely-executed
check is equally valid, as long as `evidence` names it.

**The threshold and the advisory nature.** The engine emits a `premise_unproven` detent when
provenance is `read` **and** the RESIZED t-shirt (after the symmetric-resize step, not the raw
gut-read) is above Medium — **L or XL only; M itself never fires it.** A second detent,
`premise_not_applicable`, fires under the same L/XL-only threshold when provenance is
`not-applicable` instead — its purpose is the same "leave a queryable trace" one, but for a claim
that this ask has no mechanism to verify at all rather than a claim that verification was skipped.
Both detents are purely **advisory**: exactly like the D5 shape-gate and the route table above,
neither changes the resolved `route` nor populates `xl_exit`. The commit-time coverage gate is the
standing precedent for this shape: a detent that surfaces a concern without gating the room it
fires in, ruled advisory-not-blocking for the same shift-left-without-hard-gating reason. It
shares the "the lobby wins by being cheap, never by refusing entry" principle already load-bearing
throughout this page (§ The turn-one arrival advisory).

## The hard gate — no named-reason override on the route

**The t-shirt→route map binds absolutely. There is no named-reason override, and therefore no
ratifier.**

Two sanctioned correction mechanisms already exist for a route that feels wrong, and both change
the *input* (the size) rather than the *output* (the route): the symmetric resize, which fires
before the route resolves, and the plan→sizing return edge (below), which fires after substrate
verification has produced real evidence. A free-text override would restore exactly the
in-the-head routing this lobby exists to discharge — the same failure mode the D5 encoding
(§ above) was built to keep out of the shape-or-not decision, recurring at the route level instead.
If the route feels wrong, the size read was wrong: fix the size, with evidence, and let the table
re-resolve.

XL is not an exception to this. `pm-decision` is a *routed outcome*, and the PM's pick is recorded
in `xl_exit` — it is not an override of the map.

## The plan→sizing return edge — modelled on the plan⇄spike trampoline

A **typed loop-back to `coordinator:sizing`**, deliberately modelled on the existing plan⇄spike
trampoline rather than invented fresh — the same shape of "authoring pauses, hands off to a
narrower ceremony, and resumes carrying that ceremony's output" already proven load-bearing there.
Explicitly not a third exit from Branch B, in the same way the eighth dimension is not.

**Fires when all of these hold:** the seven-dimension checklist is all-green, the eighth dimension
is green, and the verified scope is materially smaller than the ask implied — mechanically: ≤2
files in scope, no new abstraction, an existing test surface already covers it, and no cross-repo
contract.

**Action:** invoke `coordinator:sizing`, feeding `--probe-signal collapse` and the Branch B
findings as `--scout-evidence`.

**Resume semantics — full disposition, all six possible re-routes.** The re-invoked
`coordinator:sizing` can return any of its six routes; each is disposed here explicitly, none
falls through silently:

- **`plan`** → Branch A's conform-detent fires, but resumes at **Branch C**, not Branch B — Branch
  B already ran and came back all-green on this pass, which is this edge's own firing
  precondition, so re-running it would both waste the work already done and be the thing that
  would let the collapse row fire twice. Full terminal at Exit.
- **`spec-dispatch`** → resumes at Branch C at S-lane weight (`scope_mode: spec-dispatch`), for the
  same reason as above. Light terminal at Exit.
- **`dispatch`** → the scope collapsed below plan-worthiness entirely. Abandon this plan-authoring
  pass and dispatch directly instead. This is clean by construction: `scaffold-plan` runs at the
  Exit, so at this point in Branch B no plan artifact has been scaffolded or committed — there is
  nothing to unwind.
- **`shape`** → the re-size tripped the shape-entry gate: the problem turns out not to be converged
  after all. Leave `plan` for `coordinator:shape`; its own exit gate chains back here.
- **`roadmap` / `pm-decision`** → **unreachable by construction from this edge.** The edge feeds
  `--probe-signal collapse`, which can only move the t-shirt down, and neither `roadmap` nor
  `pm-decision` is reachable by collapsing. If one comes back anyway, the probe signal was
  mis-fed — stop and re-read the Branch B evidence rather than proceeding on it; this is a
  diagnosis to make, not an ordinary disposition to apply.

**Termination argument, stated rather than merely asserted:** the edge fires at most once per
plan-authoring pass. Check it against the six-way disposition above: `plan` and `spec-dispatch`
resume at Branch C, not Branch B, where the collapse row lives; `dispatch` and `shape` exit
`plan`-authoring entirely; `roadmap`/`pm-decision` are structurally unreachable from this edge. In
every reachable outcome, Branch B — the collapse row's own home — is never re-entered, so the row
cannot re-evaluate. A plan→sizing→plan ping-pong is structurally impossible, not merely unlikely.

**No-sizing-object case:** an express-lane ask deliberately leaves no sizing-object behind
(`coordinator/skills/sizing/SKILL.md` Step 4). The return edge then invokes sizing as a *fresh
intake* — there is nothing to update, and sizing writes a new object carrying the Branch B
evidence. "No object to update" is the ordinary case here, never a failure.

## Relationship to Branch A — the incumbent this supersedes

`coordinator/skills/plan/SKILL.md` **Branch A** ("Triage: should I plan, and at what altitude?")
is the existing, live, ratified pre-planning triage tree — trivial / impl-only / PM-axiom /
handoff-prescribed / exploration / non-trivial / architectural. It predates sizing and is not
being deleted by it.

The two operate at **different granularity** and sizing **feeds into** Branch A rather than
replacing it outright: sizing is the fleet-wide first move on *any* ask, coarser and earlier,
producing a computed route (express lane / plan / shape / roadmap). Branch A is the
finer-grained triage an ask undergoes once it has already been routed toward `coordinator:plan`
— it decides *how* to plan (which sub-branch, what rigor), not *whether* the ask needed planning
attention at all. An ask sized as "plan" arrives at Branch A already past the
trivial/non-trivial/architectural sort sizing performed; Branch A then does its own, narrower
job on top of that.

This relationship is also the concrete measuring stick for the lobby's own ergonomics AC: sizing
is only worth ritualizing if the sized path is verifiably cheaper, at real dogfood, than the
fuzzy in-head heuristic Branch A's early rows currently ask the EM to run unaided. Named here so
that comparison has a fixed, citable incumbent rather than an abstract "the old way."

## Keyword-gating reconciliation — the literal word gates the lobby, not the ceremony

The PM deliberately downgrades their own hotpath verbs — `/plan`, `/shape`, `/roadmap-plan` —
from *direct ceremony invocations* to **appetite hints the sizing lobby consumes**. On paper this
collides with the standing rule in `coordinator/snippets/em-operating-doctrine.md § How to Decide`: *"Paraphrase is
not authorization — keyword-gated primitives need the literal word."* The reconciliation resolves
the collision **without weakening that rule**:

- **The literal word still gates.** For `/plan`, `/shape`, `/roadmap-plan` the literal verb is
  still required. What changes is the **destination it gates into**: the verb routes into the
  sizing lobby with that verb's preset appetite (`sizing_assemble.route()` resolves the room from
  there — dispatch / shape / plan / roadmap), rather than invoking the named ceremony directly.
- **This is a destination redirect, not a relaxed gate.** Eventual-intent prose ("we should plan
  this out") still is NOT invocation of anything — not the ceremony, and not the lobby. Only the
  literal word admits entry, to *either* destination. Paraphrase-is-not-authorization survives
  intact and verbatim in force.
- **The still-hard-gated primitives are unchanged.** `/spinoff`, `/handoff`, `/staff-session`,
  `/merging-to-main` keep literal-word-gates-direct-ceremony exactly as before — they are NOT
  lobby-routed. Only the sizing-consumed appetite verbs change destination.

The `coordinator/snippets/em-operating-doctrine.md § How to Decide` bullet ("Paraphrase is not
authorization") carries the greppable pointer here; this section is the authoritative articulation.

## Dispatch is a non-target for conform intake — scoped and revisitable

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-077 -->
`dispatch` — a fourth candidate room alongside `plan`, `shape`, `roadmap-planning` — does not get
a conform intake, and this section records why, as a scoped and revisitable non-target rather than
a permanent law. It is reclassified this way precisely because it fails the entry test the other
three pass: there is no invocable dispatch ceremony a conform row could attach to, and Sizing Step
4 already fully specifies that route's hand-off (below) — so there is nothing left for a fourth
conform intake to add.

- **There is no ceremony to attach a conform row to.** `coordinator/skills/dispatch/` does not
  exist on disk, and there is no invocable dispatch ceremony with a SKILL.md body a conform intake
  could be added to. `dispatch` names an execution *mechanism*
  (`coordinator/docs/wiki/dispatching-parallel-agents.md`, `coordinator/agents/executor.md`), not
  a room a sizing-object could route into the way `plan`/`shape`/`roadmap-planning` do.
- **The hand-off is already fully specified — by sizing itself.** `coordinator/skills/sizing/
  SKILL.md` Step 4 pushes `route`, `detents`, and `next_move` to the operator, who authors
  the executor brief by hand from that push. That IS the conform contract for the small-ask-
  execution room `dispatch` names; it shipped with sizing's own Step 4 and needs no separate
  intake elsewhere.
- **A `route: dispatch` sizing-object is not a phantom.** On the ordinary, non-express-lane path,
  the routing engine maps small-appetite t-shirts straight to the dispatch route (`"XS":
  "dispatch"`, `"S": "dispatch"`); Step 4 of `sizing/SKILL.md` then scaffolds the sizing-object
  from that returned decision as normal — the route-resolution call itself is documented
  READ-ONLY and never performs the write. Only an explicit PM `--express-lane` signal
  short-circuits without writing an object at all — that is the deliberate small-and-obvious
  bypass the problem-set's Out of Scope section names, not a synonym for the `dispatch` route in
  general. So this section does **not** claim no sizing-object is ever produced for `route:
  dispatch` — one routinely is. Its consumer is the executor brief the operator writes from it by
  hand, not a ceremony-side conform intake; there is no ceremony on the receiving end to conform in
  the first place.
  <!-- spec-backlink: run 2026-08-06-14h38, nugget c7-079 -->
  A draft of this reasoning once claimed the opposite — that no sizing-objects are ever produced
  for `route: dispatch` — and that false claim propagated across five locations before review,
  cross-checked against the engine-resident routing assembler, disproved it: XS/S sizes route to
  `dispatch` and DO write a sizing-object on the ordinary path. Recorded here as the corrected
  claim, not the original one, so a future reader does not reintroduce the disproved version by
  citing an earlier draft.
- **Precedent, not a unilateral call.** An earlier planning artifact for this same lobby already
  ratified this exact reasoning shape for three other surfaces, declared thin because those
  surfaces fire *after* a room is already chosen, so they have no sizing-object entry contract to
  receive. `dispatch` is the fourth application of that already-accepted disposition, not a new
  override introduced here.
- **Scoped and revisitable, not permanent.** This is a disposition against the surfaces that exist
  today, not a closed category. Revisit it if either becomes true: an invocable dispatch ceremony
  is ever authored (giving `dispatch` a SKILL.md body a conform row could attach to), or executor
  briefs adopt a convention of citing a sizing-object directly (giving the hand-authored brief a
  structured intake point it currently lacks).

## The turn-one arrival advisory — how a session ever reaches the lobby door

The sections above describe what happens once an ask is inside the lobby. This section covers
the separate, narrower question of how a session's *first* incoming ask ever gets pointed at the
lobby door at all, given that sizing is a skill the EM has to think to invoke.

**The mechanism.** A one-line advisory, composed into the existing `UserPromptSubmit`
`additionalContext` envelope in `coordinator/hooks/scripts/runtime-tripwire-em-check.py`.
This is not a new hook registration and not a gate — it
is threaded through `_emit_advisory`'s shared composer via a `prompt` kwarg, rather than added at
individual call sites, so it rides all four call sites — including the 5-minute-throttle early
return and the no-dispatch-file early return — by construction. The composed line, verbatim:

> coordinator:sizing reads the size of an ask and names the room for it -- worth reaching for on
> novel engineering work; nothing here waits on it.

The advisory names `coordinator:sizing` as the default first move; nothing about it blocks,
defers, or intercepts the prompt itself.

**Turn-one-only, and why.** The PM's ruling was explicit: *this should never be nagging.* The
advisory fires at most once, ever, per session — on the first qualifying turn, and never again,
with no re-arming. A stateless design (recompute "should I show this?" fresh on every prompt) was
considered and rejected: statelessness removes the *satisfaction* condition (once shown, stay
shown) but does nothing about the *repetition* condition (don't show it again) — a stateless
per-prompt check re-evaluates blind to its own prior firing and would nag on every turn that still
matches its trigger shape. Firing at most once needs a state read, not a smarter predicate.

Implementation: a per-session cursor file in tempdir, modeled on the hook's existing throttle
sentinel. The cursor tracks ONLY "was turn one spent" — never "has a sizing landed", never any
outcome of sizing. That narrower fact is the distinction the stateless framing blurred, and
extending the cursor into tracking sizing outcomes is ratified anti-scope: it is the
fire-until-satisfied shape the PM rejected.

**The no-wall constraint.** No room may refuse to run absent a sizing-object. This is a ratified
anti-scope carried forward from two predecessor sizing plans, not a fresh decision made for this
mechanism — and it has a live enforcement test behind it,
`coordinator/tests/test_conform_intakes_never_gate.py`.

<!-- spec-backlink: run 2026-08-06-14h38, nuggets c7-076, c7-078 -->
**From prose to a pytest gate, across all four intakes.** The never-a-wall rule was originally
carried only as three-times-repeated prose — stated in each conform intake separately, with
nothing enforcing that the copies stayed in sync or stayed true. It is now discharged by a single
pytest gate exercised over all four intake surfaces (shape, plan, goal-setting, and the
sizing-authored dispatch hand-off), rather than left as unverified prose per surface. The shape
and goal-setting conform intakes ship the same four-element never-a-wall boilerplate the landed
instances already carried — one contract read as one idiom across four surfaces, not four
independent dialects that could silently drift apart. The gate fails loud the moment any future
gate-shaped intake is added without the same boilerplate, closing the gap a prose-only rule left
open. The new turn-one surfaces are covered by
their own test, `coordinator/tests/test_sizing_arrival_never_gates.py`, which asserts the advisory
string carries no imperative-blocking vocabulary (must/required/stop/before-you-may) and that the
hook exits 0 on every path, including the fire path. The advisory is deliberately an offer at the
front door, never a gate on a room: a room that hard-required an upstream sizing-object would
reintroduce exactly the wall those predecessor plans ruled out, just moved one layer earlier. The
lobby wins by being cheap, never by refusing entry.

**The two escape hatches.** The advisory does not fire on every qualifying prompt unconditionally
— two shapes suppress it:

- A prompt that invokes a skill or slash-command. The operator already named where they're going;
  the advisory has nothing to add.
- A bare-pointer ask — a filepath with little or no surrounding imperative. This hatch is
  deliberately narrow: a filepath embedded *inside* an imperative ask ("fix the bug in
  `foo.py`") does not suppress the advisory. Only a prompt that is substantially just the pointer,
  with no imperative wrapped around it, qualifies.

**Mutual exclusivity with pickup, and why it matters.** A session resuming a baton does not size —
that work was already sized when the baton was written, or was deliberately left unsized, and
either way re-sizing it on resume would be re-litigating a decision that isn't this session's to
make. The skill-invocation hatch above is not a generic "don't interrupt slash-commands" courtesy
sitting next to this concern — it *is* the mechanism that keeps the advisory from firing in every
session-opening shape that legitimately never sizes: `pickup`, `workday-start`,
`workweek-complete`. A later reader must not "simplify" the hatch away as redundant scaffolding;
removing it reopens nagging on exactly the sessions the PM's turn-one ruling was meant to spare.

**The git-root scope limit.** The host hook returns before advisory composition when there is no
git root, and separately short-circuits for subagent sessions. Consequently, an ask arriving in a
non-git cwd, or inside a subagent, never reaches this mechanism at all — it falls back to the
skill descriptions alone (see below) as its only arrival signal. This is an accepted gap, not a
defect: both cases are already outside the surface this envelope instruments.

**Why the skill-description work was the strongest lever, not a redundant belt-and-suspenders
pass.** Sizing was not the only skill claiming the arrival moment — it was the least assertive
claimant. `plan/SKILL.md` carried "writing a plan to disk without invoking this skill is a
doctrine violation", an imperative-with-penalty that beat sizing's own advisory ("invoke BEFORE
plan") on the identical moment; `shape/SKILL.md` and `brainstorming/SKILL.md` claimed the same
pre-solutioning slot with no deference at all. A model choosing between an advisory and an
imperative-with-penalty has an easy call, and it was the wrong one. All three now defer in one
identical clause — "Unsized work enters via coordinator:sizing first." Note honestly: sizing's own
description already contained a shape test that was already failing before this work started;
rewriting it was a tidy-up, not the lever. Tightening the three competing descriptions was the
change that actually moved the needle; the turn-one advisory above is the mechanism that reaches
the sessions those descriptions can't — the ones that open on a bare ask with no skill invoked
yet.

## Partial-completion crash — reaper hand-back and audit credit

<!-- spec-backlink: run 2026-08-06-14h38, nugget c7-075 -->
A prior holder of a sizing-cascade row crashed mid-execution after actually shipping four
acceptance criteria, but before stamping the row's completion state. The reaper mechanism that
reclaims an unheld row returned it to the pool looking untouched — the crash left no partial-state
marker for the reaper to distinguish "nothing done" from "done, but not recorded." A same-day
baton audit subsequently credited one of the four already-shipped commits back to the crashed
holder once the discrepancy surfaced. Recorded here as a known gap in the crash/reaper path, not a
resolved one: a row can carry real, shipped work that the reaper's untouched-looking hand-back
does not reflect, and only a manual audit currently catches it.

## Related

- `coordinator/skills/plan/SKILL.md` § Branch A — the incumbent pre-planning triage.
- `coordinator/skills/shape/SKILL.md` § Conform intake — an incoming sizing-object (route=shape) —
  the shape room's conform intake, the named block placed after the `/shape`-vs-brainstorming
  paragraph and before the `<HARD-GATE>`.
- `coordinator/skills/goal-setting/SKILL.md` § Step 1 — the goal-setting room's conform intake,
  consuming the seam contract's crossing fields.
