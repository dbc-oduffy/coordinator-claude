# What We Actually Measured

Most of coordinator-claude's design was argued, not measured. Some of it was measured, and several
of those measurements reversed a position we had already committed to in writing.

This document separates the two, because conflating them is how a project talks itself into
believing its own defaults. Everything below is split into **measured** — a real n, a real delta,
a stated method — and **changed on observed failure**, where a small number of concrete incidents
moved a decision. Both are legitimate reasons to change a system. Only the first is evidence.

If you are evaluating whether any of this is more than vibes, read the first section and ignore
the rest.

---

## Measured

### Lowering reasoning effort produced strictly better code

We had `executor` and `enricher` — the agents that write to your repository — running at `medium`
reasoning effort, on the stated rationale that "a miss lands in the repository and is discovered
later, which is what the tier is buying."

We tested it on a real security-guard bug, n=3 per arm, against a grading oracle registered before
the runs and checking both directions (does the fix work, *and* does it avoid breaking the
fail-closed case).

| Arm | Oracle pass | Output tokens | Turns | Cost |
|---|---|---|---|---|
| `low` | **3/3** | ~11.8k | 14 | ~$0.85 |
| `medium` | failed one | ~18k | 20 | ~$1.33 |

The `medium` failure is the interesting part. It over-narrowed the guard until the fail-closed
scripted-spawn case stopped denying — a security regression, introduced *while doing more work*
than the passing `low` runs, against a brief that named that exact constraint.

We then had three independent judges rank the patches blind: labelled by content hash, never told
that reasoning effort was the variable. **All three returned the identical ranking, with every
`low` patch above every `medium` patch.** Their language, unprompted: "the extra size mostly
bought risk rather than safety"; "more code, more shared-surface risk, and no more safety."

The mechanism we take from it: more reasoning effort produces a larger diff, and a larger diff has
more surface on which to be wrong. `medium` was not buying care — it was buying blast radius.

Limits, stated: n=3, one single-file fix, and one dissenting nuance the judges recorded (a
`medium` patch fixed one case all others missed). The tier is pinned in a regression test, so
raising it takes a deliberate edit rather than a drift.

### Repetition beats reasoning effort on code review

Same measurement programme, review surface. On planted defects, `low` recall was 100% against
`medium`'s 86%. On ~1,700 lines of live code scored against an adjudicated union of findings,
`low` found 3/3 confirmed issues against `medium`'s 2/3, at roughly 60% of the output tokens.

Two side-findings matter more than the tier result:

- **No single review run found everything.** Repetition buys more than tier does.
- **Roughly three-quarters of findings on already-reviewed code were rejected by adjudication.**
  Which is to say: most of what a reviewer tells you about reviewed code is noise, and if you are
  not adjudicating, you are acting on it anyway.

The one honest negative for `low`: on the single genuinely ambiguous claim, it returned three
different answers in three runs where `medium` returned one.

The measurement also caught a defect in its own instrument before publication — a JSON output mode
that returned only the last message, so findings followed by a sign-off were silently discarded
and scored as parse failures. That bug would have been published as a model difference.

### A feature was built, proven to work, and retired on its own base rate

We wanted an oracle that could tell whether a dispatched agent had actually finished. The proposed
mechanism — treat a quiet transcript as a finished one — was **disproven** against 7,863 agent
transcripts and 694,138 records: the false-positive rate ran 76.4% at a 300s threshold and 57.9%
at 1800s. Nearly flat across a 6× threshold increase. No threshold rescues it.

A different predicate did work — 99.41% correct across 7,812 finished agents, with the residual
failing in the safe direction, and the race condition measured down to 0.31% survival at a 120s
debounce.

Then we measured how often the problem it solved actually occurred: 681 fires over 26 days
concerning 6 distinct agents, against a genuine stall rate of 0.59%. A *perfect* oracle would have
converted those 681 interruptions into about 24 correct ones — every one of them reporting
something the operator had already been told.

We retired it. The working mechanism is in the git history and the feature is not in the product.

### We published a conclusion about the agent runtime and had to retract it

An earlier revision of our own research concluded that the agent roster and tool-instruction blocks
are never delivered to dispatched subagents. **That was wrong.** They are delivered lazily,
attached to the first tool result.

A probe making exactly one `Bash: echo hi` call:

| Request | Total input tokens | New tokens |
|---|---|---|
| Before any tool call | 45,258 | 34,023 |
| After `echo hi` | **60,805** | **+15,547** |

`echo hi` returns two bytes.

The retracted conclusion had a specific cause worth naming: *transcript absence is not proof of
non-injection*. The lazy delivery produces no record at all, so the instrument that found "nothing
was delivered" was incapable of seeing it. Re-measurement corrected four standing figures and
falsified two other claims we had been repeating.

### An "order of magnitude" claim that did not survive re-pricing

We believed agent shell fan-out dominated machine degradation by two orders of magnitude. A census
of 1,389 transcripts, 62,487 shell calls and 203,819 process spawns says otherwise: the honest
band is 8.2×–35.8× on macOS spawn pricing and only **1.1×–2.1× on Windows pricing**. We had been
quoting the flattering number.

What the census *did* establish is a distribution problem rather than a mean problem — a p99 of 12
forks per shell call, max 61 — and that our existing guards were pointed at the wrong thing,
reaching 0.44%, 1.4% and 3.2% of their own target corpora respectively. The guard layer was not
under-tuned; it was aimed wrong.

---

## Changed on observed failure

These changed real behaviour on a small number of concrete incidents. They are honest engineering
records. They are not measurements, and we would rather say so than let them borrow credibility
from the section above.

- **Write confinement, removed then partly reinstated.** We removed a guard that blocked delegated
  edits, because it was overriding explicit intent. Twelve days later the always-on instruction
  surface grew **28,328 → 36,229 bytes (+27%) in a single wave**, from many individually-plausible
  additions across parallel agents. The byte delta is real and traceable; n is one wave. The guard
  came back for exactly one path class, with an admission rule so it cannot quietly become general.
  The failure it addresses is a *growth rate*, which after-the-fact review structurally cannot hold
  down.
- **Subagent shell confinement, two classes.** Four dispatched agents in one run reported a
  confinement as an obstacle; one returned BLOCKED on a false premise about its own permissions.
  Our own record calls this "the measured cost." It is four anecdotes, and the word oversells it.
- **Test-suite invocation authority.** Subagents may not run full test suites. The reasoning —
  concurrent suites on a shared checkout produce concurrency artefacts, not real defects — is a
  mechanism argument we believe. There are no incident numbers behind it.

---

## The reversal is the point

The episode we would actually point a sceptic at has no clean number in it.

We dropped six reviewer agents to low effort on cost grounds, with no data. Evidence arrived
suggesting that was wrong, and we raised them back. Within hours we reverted that, on **no new
data**, by re-weighing what we already had against a better question — not *"did the cheaper arm
miss things"* (it will) but *"did it miss things nothing downstream recovers."* Under that filter,
two of three misses were recovered by later gates, and the third was a different agent's job to
catch.

Three things came out of that round trip:

1. **The cost had been weighed on the wrong number.** The change was +25% tokens but **+81%
   wall-clock**. We had been looking at the mild number while the severe one was latency.
2. **The judge was conflicted, and we said so.** The agent adjudicating the arms was itself running
   at the tier under evaluation, concluding that tier was worth paying for. Flagged in advance, and
   still under-discounted in practice.
3. **The setting was deliberately left unpinned in the regression suite, in both directions** —
   because pinning it would launder thin evidence into a hard gate.

We are not claiming the reversal was well-measured. It was not; it was n=1 on a self-authored
subject. We are claiming that a system which will publicly revert itself within a day, name its own
conflicted judge, and refuse to enshrine a result it does not trust, is doing something different
from one that only ships confident-sounding conclusions.

The failure mode this whole document exists to resist is the one we keep catching ourselves in:
**an agent reporting success is not evidence of success.** We have measured sub-agent waves
reporting 9/9 batches succeeded while 40 of 135 assigned items were actually read; a budget test
that summed source and read green while the real artifact was already over limit; two independent
probes reaching the same wrong conclusion because both had read our own documentation asserting it.
Every one of those was caught by a mechanical assertion against what was actually on disk, and by
nothing else.

---

*Records behind each item live in the source repository's `docs/decisions/` and `docs/research/`.
Where a record asserts an empirical basis it does not carry, we have said so above rather than
citing it.*
