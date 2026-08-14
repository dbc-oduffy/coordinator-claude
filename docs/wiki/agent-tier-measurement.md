# Measuring Whether an Agent's Tier Earns Its Cost

> Every agent definition carries a `model:` and an `effort:`. Both are guesses until someone
> measures them. This page is the method for replacing the guess with evidence, the instrument
> defects that make such a measurement quietly wrong, and the shape that stops the decision from
> drifting again afterwards.

## The problem this solves

`model:` and `effort:` get set by two different passes at two different times. Promote an agent's
model and its old effort comes along unexamined; nothing revisits the pair, and no artifact
notices. The result is a fleet where a large fraction of agents sit in one default bucket that
nobody chose deliberately.

The reasoning used to defend those defaults is usually plausible and usually untested. A typical
form: *these agents do semantic matching, and their false-negative rate is what the review pipeline
pays for, so they need the higher tier.* That is a real argument. It is also a hypothesis, and it
is cheap to test.

## The method

**Run the tiers as arms against the same task and score them against a key you derived rather than
wrote.**

1. **One subprocess per run**, with the model and effort set per arm. A top-level probe sets the
   same model-side parameter an agent definition's `effort:` does, so it measures the same thing
   without mixing parent and child token accounting.
2. **Inline the fixture into the prompt and deny tools.** If the agent reads fixtures from disk,
   tool-use variance and permission handling become part of what you are measuring. Inlining leaves
   model and effort as the only variables.
3. **Derive the answer key from the fixture data structure**, never write it alongside. A key that
   drifts from its fixture invalidates every arm equally and looks exactly like a real result.
4. **n≥3, and preferably n≥5.** Single runs are badly misleading on anything with ambiguity in it.
5. **Report cost and quality together.** A quality result with no price attached does not answer
   the question anyone actually asked.

### Build headroom into the fixture

A fixture that every arm solves perfectly discriminates nothing. That is worth knowing — it means
the work does not need the higher tier — but it cannot support a conclusion about anything harder.
Confirm the fixture separates *something* before trusting a null result from it.

For a matching-shaped task, headroom comes from the failure modes real matching trips on:

- a **superseded** document whose rule was reversed, where the naive answer matches the old rule
- **scope-qualified** rules that only bite under a stated condition, with claims falling on both
  sides of that condition
- **composite** conflicts visible only by reading two documents together
- **lexical bait**: claims whose vocabulary matches an irrelevant document, and conflicts whose
  vocabulary matches nothing in the document that actually governs them

### Prefer a real surface to a synthetic one

A planted-defect fixture measures recovery of defects someone already knew about. Pointing the arms
at real code answers the question that matters, and there is no answer key — so build one:

pool every arm's findings, cluster them by location, have independent judges rule each cluster real
or not, then score each arm on how much of the confirmed set it recovered. The adjudicated set is a
genuine findings list as well as a measurement, so the spend produces two things instead of one.

### Judge quality blind, and separately from pass/fail

An oracle answers *does it work*. It cannot answer *is the more expensive output better*. For that,
put the outputs in front of independent judges — and blind them: label each output with a hash of
its own content so label order carries no information, and do not tell the judge that tier is the
subject. Agreement across several judges is what makes the ranking trustworthy; report the
agreement rate, not just the winner.

## Instrument defects that produce confident wrong numbers

Each of these fails silently. None of them errors.

- **Reading only the final message.** A non-interactive run typically returns just the last
  assistant message. On any long task the model reliably produces its output and then closes with a
  short sign-off, so the payload is discarded and scored as a parse failure. Stream the run and
  concatenate every assistant text block.
- **Ignoring the tool channel.** Where the harness offers a structured reporting tool, a review
  model will reach for it rather than printing the requested JSON — then sign off with "reported
  above", leaving the text channel empty. That is the model behaving sensibly. Harvest the tool
  payload as a first-class channel instead of forbidding it and measuring a fight.
- **Colliding answer keys.** Two expected findings on adjacent lines, matched with a tolerance
  window, let the first absorb the second's credit so the second can never be scored. Give a
  multi-line defect multiple anchors, or the tolerance eats your recall figure in every arm at
  once.
- **Attributing a pre-existing failure to your change.** Before concluding that a change broke
  something, verify the same check against the unmodified baseline. Test suites also carry
  order-dependent flakes, so a failure that appears only in a batch run may be collection order
  rather than your edit.

## What the method found

Reported so the numbers are usable, not to be taken on faith — reproduce them rather than cite them.

- On **mechanical extraction**, every tier scored identically. This work does not need a higher
  tier.
- On **semantic matching against a supplied corpus**, including superseded, scope-qualified and
  composite cases, the lower tier recovered every conflict the higher tier did, at roughly half the
  cost. The false-negative argument for the higher tier did not survive contact with a measurement.
- On **code review**, the lower tier matched or beat the higher tier on defect recall. The higher
  tier's misses were the most judgment-dependent items, which reads as a different reporting
  threshold rather than a capability gap — but it is not evidence that the higher tier catches
  more.
- On **implementing a real fix**, the lower tier passed a held-out oracle every time. The higher
  tier produced substantially larger diffs, and one of them broke a fail-closed security invariant
  the brief had explicitly named. Blind judges ranked every lower-tier patch above every
  higher-tier patch, unanimously, and judged the extra size to have bought risk rather than safety.
- The one real cost of the lower tier: on a **genuinely ambiguous** item it was less stable,
  returning different answers across repeats where the higher tier was consistent.

That last point is the honest shape of the result. The lower tier is equally accurate on decidable
questions and noisier on ambiguous ones. That is an argument for keeping judgment-shaped work at
the higher tier — not for paying the higher tier on matching-shaped work.

<!-- provenance: 2026-08-06-14h38 / c12-014 -->
**A field case where a demotion had to be reverted, and why it was less clean than it looked.**
One field cycle ran a persona at the lower (low) tier in production and found it missed
three major issues that the medium tier caught. Before treating that as a simple "restore the
higher tier" result, the misses were traced individually: two were recovered by a downstream
check regardless of which tier produced the miss, and the third was actually in a different
agent's remit — a prior-art-checker that was reading only 2 of roughly 257 wiki files before
deciding a claim was novel. The checker was fixed to read more of the corpus and to check
negative-existence claims explicitly, which is a capability fix, not a tier fix. Separately, the
persona tier was still moved back to medium, because the measured cost of the higher tier here
was concrete — about +25% tokens and +81% wall-clock — and that latency cost was accepted as
worth paying rather than argued away. The standing rule that came out of it: an M-shaped plan
carries an M-tier minimum. The lesson generalizes past this one case: when a tier demotion
produces a miss, attribute the miss to the actual component responsible before concluding the
tier was at fault — a demoted tier and an under-scoped downstream checker can produce the same
symptom.

**The counter-intuitive finding is worth stating plainly:** more reasoning effort produced more
code, and more code produced more opportunity to break something. Where the task has a right answer
that a smaller change reaches, the extra tier is not buying caution.

## Making the decision stick

Measuring once and editing some frontmatter fixes today's values and nothing else. The pair drifts
apart again the moment someone changes a model.

The shape that holds:

- **Record the pair as one decision, in one place**, together with the reasoning that justifies it.
- **Derive effort from a band, not per agent.** Group agents by the shape of the work; the band
  carries the tier. Changing one agent's effort then means either moving it to another band or
  arguing the band — both visible edits. Hand-tuning a single agent is how the drift starts.
- **Gate it.** A test that fails when frontmatter and the recorded decision disagree turns a model
  change red until the pair is reopened. That is what makes the coupling structural instead of
  remembered.
- **Enforce the ceiling in the gate too**, not in prose. A tier limit that lives only in a document
  is a tier limit that gets exceeded.

The test to apply to any rule like this one: *what artifact discharges it?* If the answer is "the
operator remembers," the work is not finished. A paragraph reading "revisit effort when you change
model" is the failure this whole mechanism exists to replace.

## Negative spec

This page is about **whether a tier is right**, not about how to write the prompt an agent runs
(prompt authoring), nor about how much context a dispatch costs (dispatch economics). It shares
only a subject with those.

It also does not license measuring tiers above whatever ceiling the operating range sets. Where a
tier is excluded by a spending decision rather than a capability one, no experiment can overturn
it, so gathering data to argue for it spends money on an unusable answer.
