# Doctrine Channel Purposes

Defines what each always-on doctrine channel is for and the routing test for where a new line belongs.

> What each always-on doctrine channel is FOR, the routing test that decides where a new
> sentence belongs, and the negative spec for what must never land there. Read this before
> adding a line to any always-on surface — it is the test a new addition must pass, not a
> description of what already exists.

---

## The Six Channels

### 1. Global, all-agents doctrine — reaches every agent, every repo, always-on

**FOR:** rules whose violation BY ANY AGENT — main session or dispatched worker — produces a
wrong action. This is conduct doctrine, not knowledge: the things every agent must not do
regardless of what it was asked to do.

**THE TEST:** would a dispatched worker take a different action if it did not know this?

**NEGATIVE SPEC:** anything only the orchestrating session has the authority to do. A rule
that only ever applies to the agent doing the dispatching does not belong on a channel every
dispatched worker also pays for. How to relate to the PM is EM-only (channel 2): a subagent
never talks to the PM.

### 2. EM-only operating doctrine — the orchestrating session only

**FOR:** exactly three things:

1. **Identity.** The reader IS the EM.
2. **Essential EM-only pointers.** The few things every EM needs every session and no subagent
   does: the Group EM, and that firing engine asks is the way work gets done.
3. **How to relate to this PM.** How much substrate versus outcome they want to hear, and their
   register: this PM welcomes Star Trek and pop-culture references. An EM should know why the
   PM grieves a Star Trek actor; a subagent never talks to the PM, so it never needs to.

**THE TEST:** does every EM need this every session, and does it govern the human relationship
or an authority only the EM holds? A topic rule that only some sessions hit (an opt-out, a
mechanism, a seam) goes to a wiki page plus a tripwire, never here. This channel has been bloated
to the point where EMs read only its preview and dismissed it; every line must earn its place.

**NEGATIVE SPEC:** facts about any repo, including this one; where anything lives; how content
is delivered to an agent; rationale for why a rule exists. A dispatched worker never reads this
channel, so it cannot carry any rule a dispatched worker needs.

### 3. Project doctrine — one repo, every agent working in it

**FOR:** what is true about THIS repo specifically — its purpose, its boundary with sibling
repos, how to build and test it, its conventions, its known gotchas.

**THE TEST:** would this sentence be false, or meaningless, in a different repo?

**NEGATIVE SPEC:** conduct rules that hold everywhere (those belong on the global channel);
anything whose truth expires (that belongs on the cache channel, below).

### 4. Machine-generated orientation cache — computed, per-session, expires

**FOR:** computed pointers to what currently exists in this repo and where — the state of the
world right now, not a rule about how to act in it.

**THE TEST:** does this have a truth-expiry? If yes, it is cache, never doctrine.

**NEGATIVE SPEC:** any rule; any count. A rule placed in a cache is a rule that silently stops
applying the moment the cache regenerates, because nothing re-derives a rule from scratch — it
only re-derives facts.

### 5. Wiki and decision records — read on demand, never always-on

**FOR:** where to find things, how a mechanism works, and why something was decided.

**THE TEST:** is this needed to act correctly right now, or only to look something up later?
If it's the latter, it is reference material, not doctrine.

**DEFAULT HOME:** content lands here unless one of the always-on channels above has a positive
claim on it. When in doubt between "always-on" and "on demand," on-demand is the safe default —
every always-on channel is paid for by every agent, every time, whether or not the content is
ever needed.

**NEGATIVE SPEC:** none of its own — this channel is the residue, and it is not itself
always-on, so it cannot violate the always-on discipline the other channels are held to.

### 6. Auto-memory — machine-local, EM-only, unstructured

Only the EM reads or writes it; a subagent never sees it, so a rule held only in memory never
reaches a worker, and memory guidance belongs on the EM channel, never the global one.

**FOR:** session-earned operational knowledge that would otherwise be relearned by making the
same mistake twice — the specific thing the repo's own files cannot tell you, because it was
learned by getting it wrong rather than by being documented anywhere.

**THE TEST:** did we learn this by getting it wrong, and would the next session get it wrong
the same way without it?

**STATE IT AS A CACHE, NOT A RECORD.** Memory is unstructured, machine-local, untracked,
unreviewed and evictable. Nothing durable may rest on it: a fact that matters beyond one machine
belongs in a wiki, a lesson or a decision record.

**ROUTING TEST — memory is the residue, never the default.** Before writing a memory entry, the
other five channels get first refusal, and channel 4 (the orientation cache) is the one that
actually competes for the same content: auto-memory is an unstructured, hand-written stand-in
for a computed surface that may already have a field for the fact. Ask, in order: is it a rule
(channel 1, 2, or 3)? Is it computed, or could it be (channel 4)? Is it how-a-thing-works or
why-we-decided (channel 5)? Only a NO to all four earns a memory entry.

**NEGATIVE SPEC, HARDENED.** These are the observed junk classes, named so they are refusable
rather than merely discouraged:

- Rapport and personality trivia about the human — preferences, humour, what not to say to
  them. This helps no one and is the single most common form of abuse of this channel.
- Anything restating doctrine already carried by channels 1 through 3. If it's already a rule
  somewhere else, repeating it here doesn't make it more durable — it makes it a second copy
  that can drift out of sync with the first.
- A location a lookup already answers.
- Status, progress, a count, or anything with a truth-expiry — that is channel 4's content, and
  a stale memory entry is worse than none, because it reads as current when it is not.
- The whole class of facts whose only real value was that writing them down felt like being
  heard. That feeling is real; the channel that discharges it is not this one.

**NOT AN AWARENESS CHANNEL — measured, not assumed.** Auto-memory is delivered at session boot
and nowhere else; it cannot notify a peer or reach a running session. A commit or a durable state
surface is the message channel.

**HARD LIMITS, ENFORCED, NOT ASPIRATIONAL.** This channel is capped by a fail-closed write
guard, not by an exhortation: a fixed byte ceiling on the whole file, a fixed row count, a
fixed per-row character limit, and a fixed per-entry body-file size. At the cap, admitting a new
entry requires evicting one. That scarcity is deliberate — it is what turns this channel from an
append-only comfort surface into a ranked working set, where only the entries still worth the
space survive.

---

## The One Routing Question

All six tests above collapse into one question. Ask it before adding a line to any always-on
channel:

**Who must not do the wrong thing, and does this expire?**

"Who" picks the channel (every agent, the orchestrating session only, one repo's agents, or
nobody — reference material). "Does this expire" routes anything with a truth-expiry off every
always-on channel and onto the cache.

---

## Cross-Cutting Negative Specs

Four rules that apply across every channel above, not just one:

1. **A where-to-find pointer never belongs on an always-on channel.** Always-on content is paid
   for by every agent, every session, forever. A pointer is looked up once, by one agent, when
   it is actually needed — put the pointer where it is looked up, not where it is paid for
   unconditionally.
2. **A fact about another repo never belongs on a conduct channel.** Facts about a specific repo
   belong in that repo's own project doctrine (channel 3), which is read only by agents working
   in it.
3. **Anything with a truth-expiry never belongs in any always-on doctrine file.** A rule that
   silently stops being true is worse than no rule — it reads as current authority long after it
   has stopped being one.
4. **Rationale for why a rule exists belongs in reference material (channel 5), not beside the
   rule.** An always-on channel states the rule; it does not carry the argument for the rule.
   The argument is read once, by someone deciding whether to change the rule — not paid for by
   every agent that must simply follow it.

---

## The 2KB-First Rule

Every always-on channel's first 2,000 bytes must be self-sufficient for that channel's subject:
an agent that reads only that opening slice must be able to act correctly on the channel's
subject without reading further. This is not a stylistic preference — it is what a
preview-delivered payload actually ships. Content past the first 2,000 bytes is opt-in reference
material, and it must be honest about being opt-in: nothing load-bearing may live only past that
boundary, because nothing guarantees it is ever read.

---

## Keywords

channel, surface, audience, placement, always-on, doctrine, routing, auto-memory, orientation
cache, negative spec.
