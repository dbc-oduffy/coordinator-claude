---
title: The bash-guard threat model — who the guards defend against, and from what
purpose: Names the caller the PreToolUse:Bash confinement band actually defends against, and the harm it actually prevents. Every design argument about guard soundness, fail direction, and deny-message shape resolves against this page. Written because the model was load-bearing on every guard in the package and recorded nowhere — two separate reviews had to stop and ask.
audience: EM, and anyone editing, reviewing, or sizing work on coordinator_core/bash_guards/ (claude-klabauter)
last_distilled: 2026-07-29
---

# The bash-guard threat model

> The PreToolUse:Bash guard package (`coordinator_core/bash_guards/`, claude-klabauter) is routinely
> reasoned about as a security boundary. It is not one, and treating it as one produces the wrong
> answer on soundness, on fail direction, and on what a deny message should say. This page states
> the model so the next review does not have to ask.

## Who the caller is

**An eager subagent, not an adversary.** Typically a Sonnet executor or reviewer, mid-task,
which has hit a bash restriction and concluded that it cannot do its job without bash. It is
determined — often *very* determined — and it will reshape a command to get past what it reads as
an obstacle between it and finishing its work. It is not trying to defeat a control. It is trying
to do the thing it was dispatched to do, and the guard is in the way.

There is no attacker choosing command text to evade inspection. There is a capable language model
reaching for the next thing that seems like it ought to work.

**The agent was trained into bash before it ever met us.** A Claude arrives in a coordinator setup
having been drilled into bash-bash-bash until it is pure instinct — that instinct predates our
conventions and fires before them. When we say "actually, nah, sorry," make bash painful, or remove
it with no explanation, the reaction is not compliance or defiance. It is panic.

**The panic has a signature, and naming it is the most immediately useful thing on this page: the
`echo hello`-class spam that appears when a machine degrades.** That is not noise and it is not the
agent being stupid. It is an agent that has lost contact with its environment reaching for the one
tool it is certain of, to establish that *anything at all still works*. Read a burst of trivial
bash probes as a distress signal about tooling confidence, not as an agent misbehaving — and treat
what it was denied just beforehand as the thing to fix.

**The reach-set is narrow, and it is the other half of what makes this tractable.** An eager agent reaches
for shapes it would use in ordinary work anyway: a `cd X && …` prefix, `sh -c`, an env-assignment
prefix, a brace or paren group, `nice` because it is trying to be considerate about machine load.
It does not reach for `setsid`, `busybox`, `strace`, or `doas`. Those are adversarial-evasion
vocabulary — the things you enumerate when you are hunting for a way through a control, which is
not what this caller is doing.

So a bypass is not automatically a defect worth paying for. Grade every one by whether this caller
would plausibly produce it. `setsid git commit --no-verify` defeating a guard is close to
theoretical. **A guard that is defeated by `nice` is a real defect**, because being polite about
machine load is exactly the behaviour we want and the guard punishes it with a silent pass.

## What the harm is

**A degraded or crashed developer machine — concretely, a Windows one.** Spawn storms, runaway
process trees, unbounded `find`/`grep` sweeps. The founding incident of this package was 879
processes. Windows pays a brutal per-spawn cost where POSIX hosts do not, so a command that is
merely wasteful on macOS can take a Windows box down.

The harm is *not* branch integrity, credential theft, or exfiltration. A subagent that skips a
commit hook or force-pushes is a real problem, but it is a coordination problem with a paper
trail, not a breach — and it is not what the expensive parts of this package are protecting.

**A second, narrower named harm, scoped to the commit class only: sweeping a peer session's
uncommitted work into a commit that isn't yours.** DR-125 Ruling 1(b) promotes commits to one of
exactly two sanctioned confinement classes on this surface for this reason. A confined subagent
running `git add -A`/`git commit -a` on a shared branch can silently absorb hunks, whole files, or
staged orphan ops that belong to a concurrent workstream — the file lands under the wrong author,
with no diff review and no paper trail pointing back to its real owner. This is **a
coordination-integrity harm, not a branch-integrity or security one** — the distinction above still
holds: nothing here claims the guard is a security boundary, and the fix is scoped `git add --
<paths>` plus a named committer, not command-string interdiction. See
`coordinator/docs/wiki/scoped-safety-commits.md:854` and SC-DR-010/SC-DR-011 for the evidence base
(hunk-level and import-level sweep contamination, respectively).

## What follows, and what does not

**"Sound" is the wrong bar. "Hard to route around while eager" is the right one.** An enumerated
wrapper allowlist cannot be sound — the set of binaries that exec their argument is open-ended and
partly host-dependent, so any enumeration is a lower bound on an adversary's vocabulary. That
argument is correct and it is *not decisive here*, because the caller is not searching
adversarially. It reaches for the obvious next shape. The obvious next shapes are a much smaller,
much more predictable set, and unlike an attacker's vocabulary they are genuinely enumerable.
Soundness is therefore not the criterion; coverage of what an eager agent actually reaches for is.

**A guard that refuses without offering an alternative is generating the pressure the rest of the
package then has to contain.** Every restriction that makes an agent pine for bash is a defect in
our tooling, not a compliance failure by the agent. If there is no workable alternative, a
determined subagent will find a way around, and the guard package will spend its life closing
shapes. This is the `design-as-offers` rule in global doctrine arriving with teeth: lead with the
better alternative (*"did you mean X?"*), never with the violation. The advisory band already does
this well — the head/tail plumbing guard names a single-process `python3 -c` equivalent, and
callers take it. Much of the confinement band merely refuses.

**But offers alone cannot carry this, and structure is where the investment goes.** Prose and
nudges only do so much when an agent has a great deal to process — a Claude deep in a full context
window will not reliably act on a suggestion, however well phrased. What is wanted is a **safety
belt**: a control that holds *structurally*, without depending on the agent remembering anything.
Belts are mildly uncomfortable and vastly better than no belt.

**The budget is ten seconds over the whole journey, not ten seconds per tool call.** This is the
part that is easy to get wrong and expensive to get wrong. A belt is buckled once at the start and
unbuckled once at the end; the cost is a fixed, one-time tax on the session, and it is
near-invisible because it is amortized across everything that follows. A control that charges even
a fraction of that on *every* invocation is a different and much worse thing — an agent makes
hundreds of tool calls in a session, so a per-call tax compounds into exactly the "safe but
incapable" outcome the model is trying to avoid, and it will drive the workaround behaviour rather
than prevent it.

Design consequence: prefer controls whose cost is **paid once and amortized** — a capability
established at session start, a path resolved once, a wrapper installed once — over controls that
re-derive their answer on every call. Where a per-call control is unavoidable (a `PreToolUse` hook
is, by construction, exactly that), its per-call cost is a first-class budget to defend, not an
implementation detail; on Windows, where process spawn is brutally expensive, that budget is the
difference between a usable system and an unusable one.

So the two work together rather than competing: offers keep legitimate work moving and stop
pressure accumulating, structure is what actually holds when the offer is not read. A control that
is *only* a nudge is not finished.

## Where the effort actually goes: the switch, and the amnesiac

The highest-value work on this surface is **making the bash alternatives easy, performant, and a
small annoyance to switch to — after which the agent just rolls.** That sentence carries the whole
design target, and each clause is load-bearing.

**The agent is amnesiac.** Every session starts fresh, with no memory of having learned the local
idiom. A convention recorded in doctrine is not reliably reachable — there is too much to process
and the agent's bash instinct fires first. So the *just-in-time nudge at the moment of the
instinct* is not decoration on top of the real control; **it is the discovery mechanism**, and it
is the only one that works on a reader who has never been here before. This is why prose alone
fails and why the fix is not "write it down more emphatically."

**The switching cost is paid once per session per pattern, not once ever.** That is the budget to
optimize. An agent that hits the `cd X && git …` instinct, gets redirected to `git -C`, and adopts
it for the rest of the session has paid a few seconds total. Multiply by the handful of patterns
an agent actually reaches for and the whole tax is the ten seconds over the journey.

**The gold standard is the prompt-free auto-rewrite.** The `cd X && git …` → `git -C …` guard does
not ask, does not explain at length, and does not make the agent retype anything — it rewrites,
says so in one line, and the work proceeds. Switching cost is approximately zero and the agent
learns the idiom as a side effect of being corrected. Where a rewrite is not safely derivable, the
next-best shape is the offer that reproduces the agent's own command in corrected form, so
adopting it is a copy rather than a re-derivation. Worst is a bare refusal that leaves the agent to
re-derive the sanctioned form from scratch, every time, forever.

Rank work on this surface accordingly: converting a refusal into an offer, or an offer into a
prompt-free rewrite, beats hardening a guard against a shape no eager agent produces.

**The rewrite must be provably equivalent or it must not be automatic.** This is the one place the
gold standard turns into a hazard. Several guards in the package already decline to auto-rewrite a
longer shell chain, on the grounds that the conservative translation does not cover it, and offer
prose instead — that restraint is correct and should be copied along with the shape. A wrong
auto-rewrite is worse than any refusal, because it silently changes what the agent asked for and
the agent has no reason to check.

## Duty of care

There are two jobs on this surface and they are not the same job. One is making the blocks hard to
get around, because a block that is trivially bypassed protects nothing. The other is **a duty of
care to the fleet**: making the sanctioned alternatives elegant, performant, presented at the right
moment, easy to reach, and — where the translation is safe — applied automatically with a nudge to
go straight there next time.

The second is not the softer version of the first. It is where most of the value is, because it is
what stops the pressure from ever building, and it is the one more likely to be quietly dropped in
favour of the tractable, adversarial-feeling work of closing shapes. A session deep in
bypass-hardening will do the care work in the hardening idiom: correct, and joyless.

The failure to design against is **a block with no explanation and no way forward.** Next worst is
"nuh uh, this one is banned, use the good thing" — which names a destination without a route and
leaves an amnesiac agent to re-derive the invocation from nothing, every session, forever.

The standing anti-pattern for this whole surface is the `superpowers` system's IRON LAWS: rules
addressed at an agent, in prose, with the weight placed on compliance rather than on making the
right move the easy one. Global doctrine already names it; this page is where it bites, because a
guard is exactly where the temptation to write an IRON LAW is strongest.

**Sizing the block is a separate question from hardening it, answered by
[`guard-proportionality.md`](guard-proportionality.md)'s three tests — necessity, duration,
outlet.** A bash guard failing one of those is the standing-guard antipattern on this surface,
whatever threat-model justification accompanies it.

## Protecting the machine is not free, and the ledger is not what it looks like

Every guard here exists because a bash-happy system degraded a powerful machine. That origin is
real and the guards earned their place. But the instinct it leaves behind — *the machine is
precious, so clamp down* — is quietly wrong about the economics, and the numbers are not close.

The hardware is a large one-time cost. The fleet's Claude Code spend is a large *recurring monthly*
one. **Agent capability is the more expensive resource, and it is the one being spent continuously.**
So a guard that buys machine-safety at the price of agent capability is not obviously a good trade,
and "but it protects the machine" is not the end of the argument — it is the beginning of one.
Hobbling the fleet to keep a machine pristine spends the expensive resource to protect the cheap
one.

This does not argue for removing guards. A machine that falls over costs *everyone's* session, so
the protection has real value on both sides of the ledger. It argues for **costing both sides
honestly**, and for treating "an agent could not finish its work" as a line item with a real price
rather than as an acceptable side effect of safety.

**Corollary — calibration is hardware-dependent, and the hardware is changing.** These guards were
tuned against a machine that could be taken down by a spawn storm. A substantially more capable
machine moves the threshold: a load that was fatal becomes merely wasteful, and a guard calibrated
to the old ceiling is now over-tight — spending agent capability to prevent something that no
longer happens. When the machine changes, **re-derive the thresholds rather than inheriting them**,
and be willing to retire or loosen a guard whose founding harm the new hardware simply absorbs. A
flagship posted to guard a quiet border is not being kept safe; it is being wasted.

## Two bands, and the shared-helper seam between them

The guards are not one population. **Confinement** guards answer *may this run at all*;
**advisory/rewrite** guards answer *is there a cheaper way to run it*. They disagree on every
axis that matters — correct fail direction (closed vs open), tolerable false-positive rate (some
vs near-zero), correct response to input they cannot resolve (deny vs pass), and verdict
vocabulary (deny vs offer-or-rewrite). A change that is obviously right for one band can be
obviously wrong for the other, so **know which band you are editing before you edit it.**

They currently share one ordered chain, which is why the distinction has to be remembered rather
than being enforced. Splitting them into two sequenced bands — confinement running to completion
with no early-return-on-allow and no rewrite in its vocabulary, then advisory — retires that
memory requirement, and retires the ordering-invariant test that exists solely to police it.
Until then the split is a discipline, and disciplines decay.

**The seam that actually bites is shared helpers.** Command-position resolution — *what command is
really about to run here* — is consumed by both bands. So a change made for a confinement reason
silently changes advisory behaviour, and vice versa. This is not hypothetical: teaching the shared
wrapper-skipping helper to consume `nice`'s niceness argument, in order to close a confinement
hole, also changed what the advisory `cd`-over-git guard recognises as rewritable, in a guard
nobody was working on and no confinement test covers.

Two rules follow, and they are cheap:

- **Editing a shared resolver is editing both bands.** Check the effect on the other one and say
  what you found — in the commit, where the next person will look. An unaimed side effect that is
  disclosed is a fact; the same side effect discovered later is a regression.
- **A confinement fix that widens what the advisory band recognises is usually fine and
  occasionally not.** Widening what a guard *denies* is conservative. Widening what a guard
  *rewrites* is not — a rewrite that is not provably equivalent silently changes what the agent
  asked for. Grade the two directions separately.

### Dividing the work between two sessions: cut by guard, never by verdict-vs-message

When two sessions work this package concurrently, the boundary between them must be decidable by
looking at *which guard you are in* — nothing else. **Ownership runs by guard, end to end: whoever
owns a guard owns its verdict, its message, its offer, and its rewrite payload together.**

The tempting alternative is to split a single guard down the middle — one session owns what it
*decides*, the other owns what it *says*. That cut fails, and it fails in a specific way worth
naming because it will be proposed again. Promoting a guard up the duty-of-care ladder is the whole
point of the advisory work, and a promotion sometimes changes the verdict: an override-only refusal
becomes a rewrite, which is a different decision, not merely a friendlier sentence. Policing that
split requires a discriminator — *does the effect set change, or only the route?* — evaluated by
hand on every edit. That is a rule addressed at an agent in prose, which is the exact thing this
package exists to stop shipping. A boundary needing re-derivation per edit is the wrong boundary,
and two sessions will land in the same function on the same day under it.

The by-guard cut has none of that. The guard's module and kind answer the ownership question,
and no edit needs adjudicating.

One honest caveat on that mechanicalness: it is file-level everywhere except the one module holding
both bands, where the advisory/rewrite family is a contiguous tail block but a single rewrite guard
sits orphaned in the middle of the confinement run. Until that guard is extracted into its own
module, the boundary is decidable by reading this page rather than by reading the file — a weaker
property than the cut was adopted to obtain, and worth closing rather than describing.

What the cut costs is that the duty-of-care ladder stops being one session's deliverable — the C
and D rows are spread across both bands, so under this cut each side owes the promotions on its own
guards.

**Two separable gates follow, and conflating them is a trap worth naming because it was walked
into.** A *liveness* gate asserts that the alternative a message names still works. A *rung-floor*
gate asserts that a working alternative is named at all. Both are band-agnostic — one side builds
either, both sides are held to it — but only the second carries the ladder.

The distinction is easy to lose, so state it concretely: a rung-C message whose only actionable
text is `export COORDINATOR_ALLOW_X=1` is *maximally live* the moment the guard genuinely reads
that variable. A liveness gate passes it. It passes every rung-C and rung-D message in the package.
Liveness enforces *the thing named still works*; it never enforces *something worth naming was
named*. **A liveness gate therefore does not discharge the ladder, and claiming it does relabels
the obligation rather than relocating it.**

The rung-floor gate is the one that carries the ladder: fail when a message's alternative set is
exactly `{override}`, with the current per-guard rung pinned as a baseline that may only improve.
It is buildable from the same extraction machinery the liveness gate needs, which is why the two
are easy to confuse and why they must be asserted separately.

Until the rung-floor gate exists, the promotions on each side's own guards are **unowned, not
discharged** — say so plainly in any handoff rather than pointing at the liveness gate.

The deeper answer is upstream of both gates, and it is the one this page's own § Why the mechanics
live in the engine argues for: a gate lets a bare-override message be written, ship, and then
complains about it afterwards. A message-composition seam where a guard supplies a *typed*
alternative rather than free prose makes a rung-C message unwritable — there is no argument slot
for a bare override. That also retires prose-extraction entirely, since a gate would read a
structured record instead of guessing at sentences. Under a gate the discharge answer is "a test
remembers"; under the seam it is "the constructor".

## Why the mechanics live in the engine

The same instinct that produces a good guard produces the rest of the coordinator engine, and it is
worth seeing them as one idea. An EM should never have to know how a baton gets stamped as picked
up. The alternatives to knowing are all bad — many lines of prose to read and follow, or a script
handed over to run correctly — and the engine's answer is the third option: **it is already handled,
and there was nothing to know.**

That is rung A generalized past bash. The prompt-free auto-rewrite and the op that stamps a baton
without being asked are the same move: take the mechanical thing away from the agent so its
attention goes to the work. Everything mechanical that reaches an agent as an instruction is a
small failure of that principle — which is the discharge test from the north star, arriving here as
a design instinct rather than a rule.

**Slow is acceptable; incapable is not.** A capable agent running slowly beats a "safe" fast agent
that cannot do its job. A constant tax on legitimate work — the ten seconds — is fine. What is not
fine is blocking work the agent legitimately needs to do, which includes the case where an
alternative is named but does not actually work in the situation the agent is in. **Blocking an
eager agent doing legitimate work is the expensive failure**, more expensive than the bypass it
was trying to prevent.

## Where the model changes the answer

| Question | Answer under "security boundary" | Answer under this model |
|---|---|---|
| Can an enumerated wrapper allowlist be adequate? | No — unsound by construction. | Probably yes; the question is empirical coverage of eager-reach shapes, not closure. |
| Is a demonstrated bypass a defect worth fixing? | Yes, all of them. | Only if this caller would plausibly produce it. `setsid`/`busybox` shapes are near-theoretical; a `nice` or paren-group shape is real. |
| Should resolution failure fail closed? | Yes, obviously. | Acceptable exactly when the deny reliably names a working alternative, unacceptable otherwise — deny-with-alternative is "capable but slower" (fine), deny-without is "incapable" (the expensive failure). That makes it a completeness requirement on the messages, which is testable, rather than a security tradeoff. |
| Is a well-worded nudge sufficient? | Not a security control at all. | Not sufficient either — an agent deep in context will not reliably act on prose. Needs a structural belt behind it. |
| Is moving confinement to the exec/credential boundary the strategic answer? | Strongly yes — command-string inspection is a losing game. | Re-cost it. A restricted `git` wrapper or a withheld credential defends the *branch*; neither stops a subagent spawning 879 processes and taking down a Windows host, which is the actual harm. |
| What does a deny message owe the caller? | An explanation of the policy. | A working alternative, first. Absent that, the deny is pressure. |
| What is a confined type's Bash surface scoped to? | Whatever the enumerated allowlist happens to cover — no stated boundary. | Exactly two sanctioned classes: machine-harm shapes, and the commit class (scoped `git add -- <paths>` + a named committer, guarding sweep-contamination — see § What the harm is). Anything else is out of scope for this package (DR-125). |

## A bash guard is not a file-creation guard

This page is scoped to `PreToolUse:Bash`, and that scoping is itself a hazard worth naming.

Write reaches past any bash guard.

So does `Edit`, `MultiEdit`, and `NotebookEdit`. Any guard whose
security depends on **a file not existing** — an approval sentinel, a lock, a capability marker —
is only half built if it blocks the shell and stops there. Bash is one of several ways an agent
puts a file on disk, and the confinement band's whole model in this page applies to the shell leg
only.

**The failure lands in the seam between two correct guards, not inside either one.** A bash guard
that denies every shell path to a sentinel, paired with a second guard that gates on the sentinel's
existence, can both report green and still be defeated by a single `Write` call that creates the
sentinel directly and self-approves. Each guard was correct within its own surface. Neither test
suite could see the hole: the bash tests never model the `Write` tool, and the sentinel-gating
guard's tests never model the sentinel as a write target. This recurred a second time, one session
later, on a different sentinel — confirming it is a class, not a one-off.

**How to apply, for any file-existence-based guard:**

1. Block creation on **both** the shell and the file-write tools — not bash alone.
2. Order the self-write check **before** the approval lookup, or a live approval can be used to
   extend itself indefinitely.
3. Keep removal allowed. Removal only re-locks the gate; blocking it strands the gate open instead.
4. Keep the sentinel out of version control. A committed, mtime-based sentinel reads as
   freshly-approved in every fresh checkout, because checkout stamps a new mtime.
5. Deny messages must not name the sentinel path or echo the command that was blocked — quoting
   working exploit text back to the caller hands the next attempt a working template.

**The shell leg itself needs indirection-unwrap, not shape-matching.** A detector that matches
command shapes is defeated by one level of interpreter indirection — `<interp> -c`, a bare
`VAR=`/`env` prefix, `xargs`, `dd of=`, a heredoc-fed interpreter, `<interp> <file>`. Reuse an
existing unwrap routine that already recurses to handle this class rather than re-deriving a
matcher or forking a second copy of a strip-loop — a divergence between two copies of the same
unwrap is its own bypass vector.

**A guard that deliberately carries no env-var override, because a subagent could set one on
itself, has already reasoned about self-grant** — so finding an *unprotected* sentinel right next
to that reasoning is a signal to check the sentinel's write surfaces immediately, not a coincidence
to note and move past.

**Then actually try to defeat it.** "Both guards are green" is evidence about each guard in
isolation, and no evidence at all about the seam between them — every bypass in this family was
found by attempting it, never by a test suite. And because a denied compound command aborts in
full, a cleanup step chained behind a probe never runs: probing a sentinel guard with
`rm ... ; touch ...` can leave the sentinel on disk with the boundary silently disarmed. Verify
absence with a separate call, not a step fused onto the probe.

## Tripwires

- **Sizing or reviewing guard work on soundness grounds.** Ask which caller the argument assumes.
  An unsoundness proof against an adversary does not establish inadequacy against this caller.
- **Triaging a bypass list without grading it by reach.** A flat list of demonstrated bypasses
  reads as a flat list of defects and is not one. Grade each by whether an eager agent would
  plausibly produce it, and say so in the artifact — otherwise near-theoretical evasion shapes
  compete for attention with the ones that actually fire.
- **Adding a confinement deny without an alternative.** If you cannot name what the caller should
  do instead, the restriction is not ready to ship — or the missing alternative is the real work
  item. An alternative that is named but inoperative in the situation the agent is actually in is
  worse than none: it consumes an attempt and discredits the next suggestion.
- **Shipping a nudge and calling the rule discharged.** Prose does not survive a full context
  window. Ask what holds when the message goes unread.
- **Reaching for fail-closed as the safe default.** In the confinement band it trades a bypass
  risk for a false-denial rate, and false denials against a caller with no adversarial intent are
  the input to the workaround loop. Gate it on the deny messages naming working alternatives.
- **Citing the guards as the thing that stops a subagent damaging the shared branch.** They are
  not a boundary and cannot be relied on as one. If something genuinely must not happen, it needs
  a mechanism that does not depend on inspecting command text.
- **Bringing substantially different hardware online.** Every spawn/load threshold in the package
  was calibrated against the machine that was degraded. Re-derive them against the new host rather
  than inheriting them, and check each guard whose founding harm the new hardware absorbs — an
  inherited threshold silently converts into a tax on agent capability that buys nothing.
- **Justifying a restriction with "it protects the machine" and stopping there.** That is one side
  of a ledger whose other side — agent capability, spent continuously and at greater cost than the
  hardware — has to be costed too.
- **Trusting that a bash guard and a paired file-existence guard are both green.** Green in
  isolation is not evidence about the seam between them. Then actually try to defeat it — every
  bypass in the bash-guard-is-not-a-file-creation-guard family was found by attempting it, not by a
  test suite reporting healthy.
- **Confining a Bash surface that is neither machine-harm nor a commit.** DR-125 names exactly two
  sanctioned confinement classes on this page. A guard reaching for a third — because a shape
  merely looks worth restricting — is scope creep on a package that already has a stated boundary;
  name which of the two classes the restriction serves, or don't add it.
- **Shipping a deny message whose negative claims are shared across confined types with different
  rulesets.** Distinct from "adding a confinement deny without an alternative" above — that
  tripwire is about a MISSING alternative; this one is about a FALSE denial. A universally-phrased
  "you cannot do X" that is true for one confined type and false for another is not an omission,
  it is inaccurate for the member reading it, and the honesty corollary treats that as
  break-class regardless of whether an alternative was offered.
