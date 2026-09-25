# AHEAD-Direction Reconciliation Protocol

The protocol for what an AHEAD schema-drift state obliges an EM to do, how long it may stand, and who closes it.

> An AHEAD state is the normal consequence of the producer moving — not a defect. This wiki
> names what it obliges, how long it may stand, and who closes it. Vocabulary without protocol
> is a gap we shipped and only found by inspection; this closes it.


## The vocabulary already exists; the protocol didn't

That machinery answers "has the producer moved?" It has never answered the three questions that
actually govern what to do about it: what does AHEAD oblige, how long may it stand, who closes
it. Nobody had written that down; the answer is below.

## 1. AHEAD is legitimate, not breakage

Treating every drift as a fire teaches people to suppress the signal — silence the drift-watch
alert, stop looking at `schema_drift_watch` output, or worse, hold the producer's bump hostage to
an unbounded consumer round-trip. **A producer moving ahead of a vendored pin is the expected
shape of a live contract, not an incident.** This premise is why the rest of this protocol reads
the way it does: every clause below exists to make running ahead *safe*, not to make it *rare*.

## 2. What it obliges — declaration, and it ends there

The producer's entire duty at bump time is to **declare** the bump and its CLASS. That duty is
already shipped, not aspirational: a standing entry under `state/cross-repo-commitments/`
records the standing commitment, and `coordinator/tests/test_vendored_schema_version_parity.py`
is the commit-time gate that enforces it mechanically (parameterized over every schema vendored
downstream by the engine, consuming the engine's own drift-watch direction verdict rather than
re-deriving parity on this repo's side).

The producer does **not** wait for the consumer to re-vendor, does not block its own bump on
consumer acknowledgment, and does not chase the consumer to confirm receipt. Declaration
discharges the producer's obligation completely. Anything past that — a "ready to read?"
handshake, a courtesy stall until the consumer widens — is the mutual-deference standoff in a
different costume; see `cross-repo-handshake-doctrine.md` § Acceptance-readiness vs.
branch-position, which names the identical pathology one layer up (branch-position vs.
readiness) and the courtesy-stall-memo tell that marks it.

## 3. How long it may stand — bounded by CLASS, via a trigger, not a clock

The bump classes in use — `top-level-array-additive`, `nested-field-additive`, `major` — carry
different reconciliation windows:

| Class | Window |
| --- | --- |
| `top-level-array-additive` | Re-vendor at convenience. No due trigger. |
| `nested-field-additive` | Re-vendor at convenience. No due trigger. |
| `major` (breaking) | Re-vendor **before the consumer's next write against that record shape.** |

**A trigger beats a deadline here.** A calendar SLA on a seam that may go quiet for weeks — no
schema bump, no consumer write, nothing happening on either side — produces theatre: a due date
ticks past on a debt nobody is actually blocked on, generating a false-urgent alert or, worse,
training the operator to ignore the alert class entirely. "Before your next write against that
shape" is self-enforcing instead: it is silent for exactly as long as the seam is quiet, and it
fires precisely when correctness starts to actually depend on the reconciliation — never earlier,
never later. This is the same reasoning `cross-repo-handshake-doctrine.md`'s bump-class carve-outs
already apply to *whether* a bump is holding; this protocol applies the same class-discriminated
logic to *how long the resulting AHEAD state may persist* once it exists.

## 4. Who closes it — the consumer, and only the consumer

**The pin is the consumer's.** The producer emitted a new shape; the consumer's vendored copy —
its own file, its own version string, its own re-vendor commit — is what actually needs to change
for the AHEAD state to close. The producer physically cannot flip a version string it does not
own in a repo it does not own.

This is not a policy choice, it is a structural fact, and it has a corollary worth stating
explicitly: **a producer that blocks on AHEAD-state closure is blocking on something outside its
control.** That is precisely the unbounded round-trip this protocol exists to abolish (§ 1-2
above). The producer declares and moves on; closure is entirely, unavoidably, the consumer's
move.

## 5. The debt must be visible — that's what makes running ahead safe

An **undeclared** AHEAD state is the actual failure mode. The AHEAD state itself is not a problem
— running silently ahead of a consumer's knowledge that it's happening is.


## 6. Escape hatch — an unclosable AHEAD state escalates to the PM

Because closure is consumer-only (§ 4), an AHEAD state whose consumer is unresponsive, gone, or
otherwise unable to act does not simply stand forever as ambient debt. Standing debt with no
available closer is not a permanent condition this protocol tolerates silently — it is a PM call.
Surface it rather than let it age out unbounded.

## Where the mechanism runs — noted, not settled here

The engine repo offered to host any mechanical stand-down/notice **emitter** for this protocol inside its
own engine, under its own decision record. This repo's position: that is very likely the right home for the mechanism —
the emitter is engine-shaped work (an op that reads state and fires a notice), and the engine's
own decision series is where mechanism-hosting decisions like this belong. But the **protocol** — the six sections above
— had to be authored first, on the producer side that was asked for it; where the mechanism
subsequently runs is the easier half of this problem and is left open for that follow-on
decision, not resolved by this wiki.

## Cross-references

- [`cross-repo-handshake-doctrine.md`](../cross-repo-communication/cross-repo-handshake-doctrine.md) § Acceptance-readiness vs. branch-position — the standing-general anti-deadlock doctrine (mutual-deference standoff, courtesy-stall-memo tell, bilateral sequencing by bump class) that § 2 and § 3 above specialize for the AHEAD-state case specifically.
- [`schema-version-gate.md`](../schema-and-validation-contracts/schema-version-gate.md) — the wire-format mechanics (`x-schema-version` / `schema_version`, major-only gating) that DIRECTION computation and the bump-CLASS table above both key off.
- [`cross-repo-communication.md`](../cross-repo-communication.md) — the messaging primitive (memo declaration, PM-relay) the § 2 declaration duty rides on.
