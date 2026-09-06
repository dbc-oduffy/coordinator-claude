---
title: "Queue Terminus Doctrine — Triage Terminates in Batons, Not Row Moves"
kind: wiki
audience: coordinator-em
created: 2026-07-23
system: queue-terminus
tags: [queue-terminus, debt-triage, bug-blitz, handoffs]
---

# Queue Terminus Doctrine

<!-- Spec backlink: docs/plans/2026-07-23-queue-triage-terminates-in-batons.md § Decision log (DEC-1, DEC-2, DEC-4, DEC-5) -->

<!-- Negative-spec: Do NOT build a parallel baton tray (state/improvement-batons/ or similar) —
     DEC-2 is one inbox, state/handoffs/, picked up by ordinary /pickup. Do NOT treat "raw
     directory count of state/handoffs/" as the inbox-fullness signal — count PICKABLE batons
     only (deployment_state: ready_to_fire). Do NOT let a terminus skill carry the clustering
     algorithm inline — prose describing HOW to compute a cluster means the op boundary is wrong. -->

This wiki is the **generalization's home**. It defines, once and queue-agnostically, the terminus
pattern every structured queue in this repo (`state/improvement-queue/`, `state/debt-backlog/`,
`state/bug-backlog/`) converges on at triage. `/debt-triage` and `/bug-blitz` cite this doctrine
rather than restating it; `docs/wiki/baton-authoring-bar.md` is the sibling wiki defining what a
themed baton owes its reader — cite that one for authoring bar questions, not this one.

## The problem this doctrine answers

Every structured queue we own terminated the same wrong way: **a row moved, and nothing became
more executable.** `/debt-triage` Step 6b `git mv`'d a `state/improvement-queue/<id>.yaml` row into
`state/debt-backlog/<id>.yaml` — same shape, different directory, no new context. The one moment
in the pipeline where an agent holds the most context about an item — triage itself — was spending
that context and discarding it rather than writing it down. See
`docs/plans/2026-07-23-queue-triage-terminates-in-batons.md § Problem` for the full origin story
(proposed by `example-cockpit-repo-em`, PM-generalized from `/debt-triage` to the queue family).

## The four outcome classes

Queue triage — for the improvement queue, the debt backlog, and the bug backlog alike —
terminates in exactly one of four dispositions per item. **Exhaustive, no fallthrough, no silent
retention (DEC-1).** An item that doesn't clearly fit one of the four is not evidence the doctrine
is wrong; it is evidence triage isn't finished yet.

1. **Solo baton** — the item alone justifies its own pickup. One `state/handoffs/` entry.
2. **Themed baton** — N items clustered by a shared thesis into one handoff carrying authored
   context (not a row list under a title — see `baton-authoring-bar.md`). This is the genuinely
   new capability this doctrine adds; nothing in the pre-existing pipeline produced this class.
3. **Immediate dispatch** — resolvable now; fire an executor during the triage session itself.
4. **Close** — won't-do, *or* an explicit park to the holding tier (`state/debt-backlog/`,
   `state/bug-backlog/`) carrying a **named reason**. Parking is a deliberate per-item disposition,
   never a default sink for items the triaging agent didn't get to. An item that just sits
   unclassified is not "closed" — it hasn't been triaged.

## Discriminator — class 3 vs classes 1/2

Adopted **verbatim** from the ratified ancestor of this pattern
(`coordinator/skills/architecture-audit/SKILL.md:196`, D5):

> The immediate-executor path requires findings that are BOTH tradeoff-free AND non-structural.
> Any finding touching a module boundary, interface, or cross-system surface is ineligible
> regardless of line count — it routes to a bundled/standalone spinoff candidate (baton).

Apply this unchanged as the class-3-vs-class-1/2 discriminator for every queue: an item is
**immediate dispatch** only if it is both tradeoff-free (no judgment call embedded in the fix) and
non-structural (touches no module boundary). Anything else — however small — becomes a baton
(solo or themed), never an in-triage edit.

## Ratified ancestor — this generalizes an existing PM ruling, it does not invent one

This is not a new posture. `architecture-audit/SKILL.md` already runs this exact shape for one
ceremony: **PM ruling D5** (`:102`, `:206-210`) retired that audit's auto-write to
`state/debt-backlog/` and replaced it with a disposition ladder — fix-now executor / bundled
spinoff candidate / escalated `/plan` — with the debt backlog demoted to holding only items the
EM/PM **explicitly chose to defer with a reason**. PM's stated rationale there: *"dedicated
pattern for that — don't bundle everything into one ceremony."* This doctrine is that same ladder,
generalized from one ceremony (`architecture-audit`) to the whole queue family
(`/debt-triage`, `/bug-blitz`), with the baton inbox (`state/handoffs/`) standing in for the
spinoff-candidate surface architecture-audit already uses.

## One inbox — no parallel tray (DEC-2)

Batons produced by any queue terminus are **ordinary handoffs** written to `state/handoffs/`,
picked up by **ordinary `/pickup`** — the same mechanism, same lifecycle
(`deployment_state: awaiting_gate | ready_to_fire | in_flight | shipped | continued | closed`), same
`/pickup` claim gate, as every other handoff in this repo. There is exactly one inbox.

**Negative-spec:** a chunk or skill that creates a second tray (`state/improvement-batons/`,
`state/triage-outbox/`, or any directory shaped like a parallel handoff queue) has misread this
doctrine. The baton IS a handoff — it needs no bespoke lifecycle machinery, because
`state/handoffs/` and `/pickup` already have one.

## "Baton inbox is low" — defined over pickable batons, not raw count

A terminus that decides whether to draw the parked holding tier back into circulation (see
§ Holding-tier draw-on-demand below) needs a definition of "the baton inbox is low." **That
definition is over PICKABLE batons — handoffs whose `deployment_state` is `ready_to_fire` —
never raw directory count of `state/handoffs/`.**

Live evidence, verified against disk at authoring time: `state/handoffs/` holds
**50** entries, of which **27** carry `deployment_state: awaiting_gate` and only **18** carry
`deployment_state: ready_to_fire`. (The plan's substrate-verification snapshot recorded 48/27/16
a short time earlier on this shared branch — the drift between that snapshot and this count is
itself the point: raw counts move for reasons unrelated to actionability, which is exactly why the
low-inbox signal must not be raw count.) A raw-count reading of "50 handoffs, plenty in the inbox"
is false — nearly half the inbox is gated on something else and not pickable today. A terminus
that gates its own draw-on-demand decision on raw count will under-park when the inbox looks full
but is actually starved of actionable work.

## The cockpit projection — `category` ships to the fleet as `workstream_type`

<!-- Spec backlink: cross-repo/archive/2026-07-23-example-cockpit-repo-em-queue-terminus-corpus-and-contract-axis.md § 4 -->

**A handoff's `category` field is emitted into the cockpit contract under a different name:
`workstream_type`. Same axis, two names, a 1:1 passthrough** — `claude-klabauter`
`coordinator_core/ops/emit/sections/handoffs.py:401`:

```python
"workstream_type": _jq_or(fm.get("category"), None),
```

No remapping table, no enum translation. Every value in `category` lands unmodified.

**The consequence that matters: adding a value to `category` is never sufficient on its own.**
The cockpit `WorkstreamType` Literal
(`coordinator_core/contract/cockpit_schema/entities/deliverable_spine.py`) is a *closed* set.

**What actually happens to a handoff carrying a value that Literal doesn't know: it is
quarantined, not crashed.** `HandoffSummary(**r)` raises `ValidationError`, which is caught
per-record at `coordinator_core/ops/emit/sections/handoffs.py:436-449` and shunted into the
emission's `malformed` bucket with a logged reason. The emission run completes. You lose the
individual baton from the wire, not the pipeline.

That is a smaller blast radius than "emission breaks" — and it is worth stating precisely,
because the *consequence for fleet visibility is identical either way*: until the Literal is
widened, the new value is filterable only by consumers reading handoff frontmatter off local
disk. Every consumer downstream of emission is blind to it. A class that is expressible in the
file but not in the wire format is not yet fleet-visible.

<!-- Negative-spec: an earlier revision of this section claimed the
     unknown value "hard-fails cockpit emission". That was wrong — corrected by claude-klabauter-em
     after they traced the per-record catch. Do not restore the hard-fail framing;
     the quarantine is real and the distinction matters when planning around it. -->

*See also `coordinator/docs/wiki/coordinator-tripwires/` if this ever needs a mechanical guard — today the
two-sided widening is a discipline, not an enforced gate.*

So the checklist for adding any `category` value is two-sided: widen the enum here, **and** memo
Claude-klabauter to widen the `WorkstreamType` Literal. The second half is the load-bearing one.

**Sharp edge worth knowing — `null` and `"uncategorized"` are different states.** A normalized
handoff has `category` backfilled (`handoff_normalize.py`'s `_match_category` defaults an
unmatched title to the literal string `"uncategorized"`), and emits
`workstream_type: "uncategorized"`. A never-normalized handoff has no `category` key at all, so
the `fm.get` misses and it emits `workstream_type: null`. Both mean "no known category" but
arrive by different paths. Treat them as one bucket unless you have a specific reason not to.

*Established by tracing the emission path, prompted by `example-cockpit-repo-em` asking
whether the two were one axis or two. The identity was previously recorded only in a docstring in
Claude-klabauter; it is written here because DoE governs the contract and the question cost two sessions an
investigation each.*

## The readiness bar a baton owes — `/pickup`-able, NOT `/mise`-autonomous

<!-- Spec backlink: docs/plans/2026-07-23-queue-triage-terminates-in-batons.md § AC15 -->

**A baton's readiness bar is `/pickup`-ability without further enrichment. It is NOT
`/mise-en-place` Phase-0 readiness, and the two must not be conflated.** They gate different
things: `/mise` Phase-0 (`commands/mise-en-place.md:37-43`) admits work a *pure Sonnet executor*
can complete unattended — criterion 3 (pure-executor agent type) and criterion 5 (mechanical
verification) exclude anything requiring judgment. A baton gates *session* work, picked up by an
EM who brings judgment to it.

**Why this matters, and why it is not a loophole.** Holding batons to the `/mise` bar sounds
stricter and is in fact incoherent with the rest of this doctrine: a terminus that may only emit
executor-grade items could never emit a themed baton whose first move is a judgment call — and
per § The terminus obligation and the baton-authoring bar, banking that judgment for the picker-up
is precisely what a baton is *for*. The operative rule everywhere in this doctrine is *the op
proposes, the EM disposes*; a readiness bar that requires the disposing already done inverts it.

**`/mise`-readiness is a per-baton property, never a terminus invariant.** Some batons happen to
be mise-grade (mechanical, footprint-declared, no open judgment). Most themed batons are not, and
that is the expected result rather than a defect to engineer away. Check a specific baton against
`/mise` Phase-0 when deciding how to *run* it; never as a gate on whether the terminus may *emit*
it.

*Established by PM ruling at the plan's post-execution AC audit, superseding review finding P2-1,
which had named `/mise` Phase-0 as AC15's oracle. The first themed baton produced by this terminus
fails `/mise` criteria 1/3/5 while being cleanly `/pickup`-able — the falsification that forced
the correction.*

## The terminus obligation

The moment of triage is the moment an agent holds the most context about a queue item it will
ever hold again — the title, the body, the surrounding queue entries, whatever cross-referencing
the triaging agent just did to understand it. **A terminus that moves a row spends that context
and discards it.** A terminus that writes a baton spends the same context and banks it — the next
agent to touch the item (the one who picks up the baton) inherits authored understanding instead
of re-deriving it from a bare row. This is the falsifiable test from the plan's problem-shape
restatement: after this doctrine ships, items leaving any triage ceremony are `/pickup`-able
without further enrichment.

## Themed batons — see the authoring bar, don't restate it

A themed baton (class 2) has its own bar for what makes it pickup-able rather than a row list
wearing a title. That bar — the negative-spec against row-list bodies, the shared-thesis
requirement, and the bundling threshold it binds to — is authored in full in
[`baton-authoring-bar.md`](baton-authoring-bar.md). This wiki names the class; that wiki defines
what discharges it. Cite, don't restate.

## Clustering — graceful degradation, EM disposes

Themed-baton clustering (grouping N queue items by shared theme) is a proposal mechanism, not an
authority — the operative rule across every queue is **the op proposes, the EM disposes** (DEC-3,
DEC-5). No clustering output is ever written as a baton verbatim; a human-equivalent judgment call
merges, splits, or discards proposed clusters before a baton is authored.

The terminus prefers, in order:

1. A **registered engine op** wrapping the clustering leg (queue-family-generic, per DEC-4) —
   the target state once the claude-klabauter-side op work lands.
2. **Degraded but still mechanical:** the shipped `detect-initiative-candidates` CLI in
   `claude-klabauter`, invoked directly. This CLI already ships title-keyword (and other) clustering
   generic over queue family (`UNATTACHED_TYPES` spans bug/debt/improvement/roadmap/handoff/plan)
   — a terminus that finds the registered op absent falls back to calling this CLI directly rather
   than either blocking or reinventing the clustering algorithm inline.
3. **EM judgment**, only if the CLI itself is unreachable. This is the fallback of last resort, not
   the default degrade target — a terminus that reaches straight for EM-judgment clustering while
   the CLI is available has skipped a real, tested step.

A terminus skill must never carry the clustering algorithm as inline prose — describing *what an
op or the CLI returns* is correct; describing *how to compute a cluster* means the op boundary
has been drawn in the wrong place, and the skill should stop and cite the CLI/op instead.

## See also

- `docs/wiki/baton-authoring-bar.md` — what a themed baton owes its reader (net-new authoring bar).
- `docs/wiki/spinoff-handoffs.md` — the handoff/spinoff lifecycle this doctrine's batons ride
  unmodified; § Spinoff Granularity — Bundle by Doctrine Class is the pre-existing bundling
  threshold the authoring bar binds to.
- `coordinator/skills/architecture-audit/SKILL.md` §§ Step 4, Step 5 — the ratified ancestor
  ceremony this doctrine generalizes.
- `coordinator/skills/handoff/SKILL.md` § Handoff Lineage —
  the `deployment_state` enum and `/pickup` mechanics every baton produced by this doctrine rides.
- `docs/wiki/initiative-govern-discipline.md` — the queue-triage carve-out for reusing the
  `initiative` FK as the clustering-graduation grouping key (DEC-3).
