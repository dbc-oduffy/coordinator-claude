# Two Repos, One System

> **Status note, up front.** This document describes the architecture coordinator-claude is built
> on. The engine repo it names, [`claude-klabauter`](https://github.com/dbc-oduffy/claude-klabauter),
> is **public** — install it from there; nothing is access-on-request any more. Install order is
> load-bearing: coordinator-claude first, then the engine. The pure-prompt flows work without the
> engine; the engine-dependent flows do not. We would rather describe the shape accurately than
> have you discover the seam by hitting it.

coordinator-claude is two things, and the second one is not a plugin at all.

- **`coordinator-claude`** — the doctrine. Skills, agents, commands, hooks, personas, wikis. Text
  a model reads.
- **`claude-klabauter`** — the engine. A control plane that produces and mutates work-state, and
  emits what we call disk-truth.

Most of the bundled skills call into the engine. It is a hard declared dependency, not a soft
one. This document is about why we cut it that way and what the cut buys, because the split looks
like overhead until you understand what it removes.

## The problem: a model re-deriving the same operation forever

Every operating system for AI engineering work has to do two very different kinds of thing.

The first is judgment. Should this be planned or just done? Is this reviewer's finding real? Is
this plan's premise still true? That work is genuinely a language problem. It belongs in prompt
text, it benefits from a large model reading carefully, and it cannot be reduced to code without
losing the thing that makes it work.

The second is bookkeeping. Claim this handoff. Stamp that frontmatter. Resolve this memo, move it
to the archive, and record who now owns the commitment. Compute which commits in this range have
review coverage. None of that is a language problem. It has exactly one correct answer, and the
answer is checkable.

For a long time we did both in prompt text, and the second kind quietly ate the system. Not
because models are bad at bookkeeping — because *prompt text is the wrong substrate for an
operation that has one correct answer*:

- **It is re-derived every time.** A model reads the instruction and reconstructs the operation
  from scratch, at full inference cost, in every session that touches it. The thousandth
  execution is no cheaper or more reliable than the first.
- **It cannot be tested.** You cannot unit-test a paragraph. You can only run it and read the
  result, which means every regression is found by a human noticing.
- **It drifts by copying.** The same instruction appears in forty agent bodies. Fixing the bug
  means finding all forty. We know the number because we counted, and we did not find all forty.
- **It fails differently on different machines.** A shell-shaped instruction that works on macOS
  can be brutally slow on Windows, where process spawns are expensive. Prompt text has no way to
  say "do this the cheap way here."

The split is the response. **If an operation has one correct answer, it belongs in code that can
be tested. If it requires judgment, it belongs in text a model reads.** The engine is where the
first kind went.

## What the split actually buys

**A bug gets fixed once.** When a state operation lives in the engine, there is one
implementation, one test, one fix. When it lived in prompt text there were as many
implementations as there were copies of the paragraph, and they had already diverged.

**State becomes checkable.** The engine emits disk-truth: the state of the work is a set of files
you can read, diff, and assert on, not a claim the model makes about what it did. This matters
more than it sounds. An agent reporting success is not evidence of success — we have measured
sub-agents reporting completion while silently dropping work, more than once, and the only thing
that ever caught it was a mechanical assertion against what was actually on disk. You cannot
write that assertion against a narrative. You can write it against files.

**Portability stops being per-instruction.** Multi-OS support — macOS, Windows, Linux, all
first-class — is a property of one Python codebase instead of a property every shell-shaped
instruction has to re-earn. Working on one host and breaking on another is a correctness defect,
and centralising the mutation path is what made it tractable to treat it as one.

**The doctrine gets smaller and better.** This is the part we did not anticipate. Once the
bookkeeping moved out, the remaining prompt text was almost entirely judgment — and judgment text
is what large models are actually good at reading. The skills got shorter and the instructions
got sharper, because everything mechanical had left.

## Graceful degradation is a real property, not a disclaimer

Not every flow needs the engine. The pure-prompt paths — reviewing a plan, running a persona
review, shaping a problem, reasoning about a diff — are text and inference, and they work without
it.

What needs the engine is anything that *mutates durable work-state*: claiming a handoff, resolving
a memo, stamping an artifact terminal, computing coverage across a commit range. Those are the
operations with one correct answer, which is exactly why they moved.

So the degradation is not a fallback mode that half-works. It is a clean line: **you lose the
state machine, you keep the judgment.** If you are using coordinator-claude to think with, that
still works. If you are using it to run a multi-session workstream with durable state, that is
the half that depends on the engine.

## Why this is not just "extract a library"

Two things make this a repo boundary rather than a module boundary.

**Different rate of change, different review posture.** Doctrine changes when we learn something
about how the work should go — often, and on the strength of an argument. The engine changes when
a mechanism is wrong — less often, and on the strength of a failing test. Those want different
gates. Putting them behind the same gate means either doctrine is too slow to fix or the engine is
too easy to break.

**One producer, several consumers.** The engine is not coordinator-claude's private
implementation detail. It is a control plane that more than one system routes state mutations
through. A repo boundary makes the contract explicit and versionable; a module boundary would have
made it an accident of import paths.

There is a cost, and we will not pretend otherwise: two repos means a dependency, a version seam,
and an install story with more steps than "add the marketplace." We think the cost is worth
paying, and the section above is our argument for why. It is an argument, not a proof.

## The commitment underneath

One rule governs the seam, and it is the one worth stating publicly because it is the one that
decays quietly:

**The publish target is a destination, never an input.** A machine holding the two source repos
must be able to generate both published distributions from source alone. Nothing may reach a
released artifact only because a previous release already put it there.

That sounds obvious. It was not true. We found a documentation page that reached the published
repo on every release only because a hook copied it *out of the previous release* and put it
back — it existed nowhere in source, and a publish from a fresh machine would have silently
shipped without it. There were smaller instances too.

It is now enforced by a test rather than by anyone remembering, and the property was verified the
only way it can be: by publishing into an empty directory on a machine that had never seen the
released repo, and checking that everything arrived.

We mention it here because it is the difference between a project that *is* open source and one
that merely *has* an open-source repo. If we cannot rebuild what we ship from what we author, then
the published thing is the source of truth and nobody — including us — can fully account for what
is in it.
