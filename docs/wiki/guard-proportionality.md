<!-- RAG-bait: guard proportionality, standing guard antipattern, when does a block earn its place, necessity duration outlet tests, advisory vs safety control, session-lifetime lock, fail-closed on a benign fact, guard needs a bypass, warn don't block, swimlane advisory -->

# Guard Proportionality

**Purpose.** A citable rule for deciding *how much* refusal machinery a fact earns: silence, an
advisory, or a hard block. It is the guard-side counterpart to
[`doctor-proportionality.md`](doctor-proportionality.md) — same question (how much machinery does
this earn?), same decision-procedure form, opposite end of the pipe: that page decides how much
*verification* a component warrants, this one decides how much *refusal* a signal warrants.

**What this is not.** Not [`guard-message-concision.md`](guard-message-concision.md), which governs
how a guard message is *worded* once the guard exists. This page is upstream of it: whether the
guard should exist at all, and in what form. Answer this one first — a beautifully concise deny
message for a guard that should have said nothing is wasted work.

## The rule

**A guard may not outlive the operation it protects.**

The failure class this names is the **standing guard**: it acquires more than it needs, holds for
the life of a session, denies on a fact that is almost always benign, and offers no outlet a
machine can take. Every instance looks individually reasonable at the moment it is written — which
is exactly why case-by-case judgement does not catch it and a named rule is required.

## Start with the harm class, before any machinery

**Ask what class of harm the guard prevents, before designing any of its machinery.** Fail-closed
defaults, wall-clock caps, `UNANSWERABLE` sentinels, ratified operator override keys, human-gated
unlock channels — that is the correct grammar for **irreversible harm**, and it is absurd applied
to a courtesy signal. Reach for it there and nowhere else.

The engine plane's path-touch claim gate is the incident of record: a **swimlane guideline** — so
an EM doesn't sweep a peer's uncommitted work or clobber a file someone is mid-way through —
built as though it were a safety control. That single mis-categorisation generated every symptom
downstream. The remedy was not tuning; it was deletion.

## The discriminator — three tests, all of which must pass

1. **Necessity.** It prevents a concrete failure the layer below does not *already* prevent. Not a
   failure it also prevents — one that would otherwise happen.
2. **Duration.** It lasts no longer than the operation it protects. A correct block is absorbed by
   retry and invisible in normal operation.
3. **Outlet.** The denied actor can state what it does next **without a human**.

The reference model is **git's own `index.lock`**: held for milliseconds, retried on contention,
prevents real corruption. It passes all three, and nobody has ever complained about it — because a
correct block is one you never see.

**Failing the duration test means remove, not shorten.** A shorter wrong block is still a wrong
block. The path-touch claim failed necessity and duration by five or six orders of magnitude —
session lifetime, minutes to hours, protecting nothing git did not already protect — and failed
outlet outright.

## The outlet rule, stated separately because it is the one most often skipped

**Every guard states what the denied actor does next, and "wait for a human" does not qualify on a
box running 50–70 concurrent agents.**

The incident: an EM asked its PM to create an unlock sentinel so that nine finished, passing,
correct tests could be committed — a human unblocking a machine, from a guard that was advisory by
design. That is not an escape hatch, it is a stall with paperwork.
[`guard-unlock-channel.md`](guard-unlock-channel.md) is the deliberate, narrow exception that
proves the shape: an operator-facing, one-shot, per-guard, per-session channel for a guard that
genuinely gates irreversible harm. Routine finished work reaching it is a proportionality defect
upstream of that channel, not a use of it.

## The signal corollary — duration governs the fact, not just the block

- **"Touched, ever" is not a signal — say nothing.** Reads count. Glances count. It is true
  constantly. One of the two incidents was a session that had only *read* the files.
- **"Edited in the last ~30 seconds" is a signal — warn, and let the agent decide.** Someone's
  hands are on it right now.
- **Past that window it is stale and means nothing.** Recency in seconds, never session lifetime.

A fact that fires constantly and means nothing most times must not sit in control flow. **And a
warn that *pauses* is the same defect in softer clothes** — an advisory that stops the actor is a
block wearing a friendlier word.

## The anti-remedies

When a standing guard hurts, the instinct is to build a legitimate-looking way around it. Four
patches, all of which were proposed for the incident above, all wrong:

- a completion-signal protocol,
- a lineage-enrollment mechanism,
- a shorter staleness window,
- a better override key.

Each patches the layer instead of deleting it. **A guard that needs a bypass is the antipattern;
the bypass becomes the real interface.** And deleted machinery must not survive behind a flag, a
config default, or a disabled branch — a dormant gate is a gate someone re-enables. Compare
`coordinator-tripwires/override-flags-as-latent-rot-signal.md` in the tripwire registry: an
accumulating override surface is the same smell read from the other side.

## Decision procedure

1. **Name the harm class.** Irreversible (data loss, corruption, an external side effect) or
   advisory (coordination, courtesy, hygiene)? Advisory ends here: **warn, or say nothing.**
2. **Necessity.** Name the concrete failure the layer below does not already prevent. Can't name
   one → no guard.
3. **Duration.** Scope the hold to the operation. Longer than the operation → remove it, don't
   shorten it.
4. **Outlet.** Write the sentence the denied actor acts on, machine-only. Can't write one → it is
   not a block yet.
5. **Only then** word the message, per [`guard-message-concision.md`](guard-message-concision.md).

## The four PM rules this page carries verbatim

- We don't block unnecessarily. We warn.
- We stay performant.
- We don't overengineer.
- Swimlane guidance is advisory by nature: it informs a decision, it never takes one away.

## Cross-links

- [`doctor-proportionality.md`](doctor-proportionality.md) — the sibling proportionality rule, on
  verification machinery rather than refusal machinery.
- [`guard-message-concision.md`](guard-message-concision.md) — downstream: how to word a guard
  that has already earned its place.
- [`guard-unlock-channel.md`](guard-unlock-channel.md) — the human-shaped outlet, and the narrow
  class of guard that legitimately needs one.
- [`concurrency-safety-patterns.md`](concurrency-safety-patterns.md) — the necessity test in its
  natural habitat: what the layer below already guarantees under concurrent writers.

<!-- Negative-spec: the three tests are a conjunction — passing two is failing. In particular, do
     not soften test 2 into "hold no longer than necessary": every standing guard's author already
     believed that of their own guard. Duration is measured against the protected operation, not
     against the author's intent. -->

<!-- seeded 2026-08-13 from claude-klabauter-em's guard-proportionality-antipattern proposal memo;
     incident evidence is that plane's path-touch claim gate, deleted rather than tuned. -->
