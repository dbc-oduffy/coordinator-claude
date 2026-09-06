---
title: Adapting your doctrine
created: 2026-07-09
type: doctrine
related:
  - .claude/em-context.md  (per-repo, § Posture)
  - coordinator/templates/postures/{precision,default,substrate-free}.md
  - coordinator/docs/wiki/posture-anchors.md  (the anchors' full text)
  - claude-klabauter coordinator/bin/render-posture-overlay.py
  - coordinator/docs/wiki/getting-started.md  (Movement 2)
  - coordinator/docs/wiki/eager-agent-calibration.md
  - archive/specs/2026-07/2026-07-09-coordinator-end-user-modes.md
---

<!-- RAG-bait: self-modification of doctrine, posture overlay, positronic net surgery, Mirror-Universe boundary, hook-hacking out of scope, managed section markers, ## Posture heading, doctrine layer vs enforcement substrate -->

# Adapting Your Doctrine

> **Data performs positronic net surgery, self-directed.** No waiting on Starfleet Engineering to
> re-architect that brain on every impulse to grow — the panel comes open and the work gets done,
> inside the parts of that design which are Data's own to touch. Your `~/.claude/CLAUDE.md` and your
> repo's `.claude/em-context.md` are that panel. Editing them — reshaping how the EM engages with
> you, what it surfaces, what it stays quiet about — is not a workaround or a power-user trick. It's
> the intended, everyday way this system is meant to be used.

This page is the doctrine reference for **self-modification of your own coordinator doctrine**: the
prose in `~/.claude/CLAUDE.md`, the posture you selected (or can select) at install and that lives in
`.claude/em-context.md`, and — further out — the skills, prompts, and triggers that make up the
*doctrine layer* of your install. It names what's encouraged, gives you a starting seed, and draws
one explicit line past which you've left "configuring a posture" and started "forking the system."

## The invitation

Every install ships an onboarding-chosen **posture** — `precision`, `default`, or `substrate-free` —
materialized as a `## Posture` block inside a marker-delimited managed section, `<!-- coordinator:posture:start -->`
… `:end -->`. That block does not live in `~/.claude/CLAUDE.md`: posture describes how you and the EM
work together, and the global file reaches every dispatched subagent too — none of which is party to
that relationship. It lands instead in `.claude/em-context.md`, inside the repo you ran the installer
from, a channel your main session reads and a subagent never does. Your chosen anchor also persists
per-machine, in `~/.claude/coordinator-identity.yaml`, so onboarding a later repo renders that same
choice into its own `.claude/em-context.md` without asking again. None of this makes the block a locked
factory setting. It's a **seed**: the starting shape of a relationship that is meant to keep evolving as
you and your EM learn what works for the two of you.

Treat the posture you picked at install the way you'd treat a first draft, not a final answer:

- **Found the ask/act line in the wrong place?** Edit the block. If the EM keeps asking about things you
  clearly want it to just do, say so in the prose — narrow the ask-threshold.
- **Want more visibility into a specific kind of decision, less into another?** That's exactly the kind
  of asymmetric tuning a single named posture can't fully anticipate. Write it in.
- **Noticed a skill or trigger phrase that doesn't fit how you talk about your own work?** Rename it,
  reword the prompt, adjust the trigger. The doctrine is prose your EM reads at session start — it is
  yours to author, the same way you'd redline a contract you're a party to.

This composes with the conversational path, too: `getting-started.md` Movement 2 walks you through
tailoring `~/.claude/CLAUDE.md` — and, for posture specifically, `.claude/em-context.md` — interactively
with your EM at your first sit-down. The installer-seeded posture and that conversational co-authoring
aren't competing paths — the installer plants the seed, the tour (and every session after it) is where
it keeps growing.

## What's in scope

The **doctrine layer** — the parts of your install that exist as prose, template, or configuration your
EM reads and reasons over, rather than machinery that runs underneath it:

- **`~/.claude/CLAUDE.md`** — your working-style notes, § Owner, § Communication Style, anything you've
  added or edited. Git-tracked, one revert away from any change.
- **`.claude/em-context.md`, in each repo you've onboarded** — your posture block. Swap anchors
  (`precision` / `default` / `substrate-free`) by re-running the installer's onboarding question, or
  hand-edit the content inside the managed markers directly. Either path is supported.
- **Project-level `CLAUDE.md` / `coordinator.local.md`** — per-repo extensions and overrides, same
  editable-and-reversible contract.
- **Skill prose, agent prompts, doctrine wikis** — if you're running a customized checkout (not just the
  shared plugin install), the wording, examples, and framing in these files are yours to adapt to how
  your team talks and thinks about its own work.

None of this requires special permission, a flag, or an escape hatch. It's the ordinary, expected way to
make the system fit you — the same spirit as the existing "extend but not weaken" rule for project
CLAUDE.md files: reshape freely, just don't strip the floor out from under yourself (more on the floor
below).

## The boundary — where configuring a posture ends and forking begins

**This wiki covers the doctrine/prose/skills/triggers layer only.** There is a real, deliberately-drawn
line past it, and it's worth naming honestly rather than leaving you to discover it the hard way.

Editing **hooks**, the **enforcement scripts** that back them, or a skill's **step-logic/mechanics** is
a different act entirely — call it *building your own Claude-Klabauter*. That's not tuning a posture; it's
rebuilding the substrate the postures sit on top of. Once you're rewriting `PreToolUse` matchers,
hand-editing a `bin/` script's control flow, or restructuring how a skill's steps gate on each other,
you've crossed from "configuring the ship's systems from the bridge" to "reopening the warp core" — and
from that point on, coordinator's updates won't reliably preserve your changes. You're effectively
maintaining your own fork, which is a legitimate thing to do (teams do build fully custom installs) but
is a deliberate, separate choice — not an everyday move, and not what this page is inviting you toward.

The **Mirror-Universe boundary**, stated plainly: your EM in the doctrine layer is still your EM —
same safety core, same floor, reshaped surface. Past the hook/enforcement/step-logic line, you're no
longer configuring your EM; you're building a different one. Know which side of that line you're on.

**One invariant survives every edit on the supported side — for the floor gates that are actually
hook-enforced.** No matter how far you push a posture — even `substrate-free`, which deliberately hides
the most machinery — the hook-backed floor gates (e.g. the ask-before-external-action gate) keep
firing regardless of what you write in your own `~/.claude/CLAUDE.md`. A posture changes what surfaces
to you and at what altitude; it never removes a hook-enforced safeguard.

> The whole floor list (verification before marking done, the PM-facing ask-before-external-action
> gate, review sequencing, and the rest) is NOT structurally guaranteed merely by living in prose —
> see `coordinator/docs/wiki/claude-md-delivery-topology.md` for the actual delivery mechanics.
> `coordinator/CLAUDE.md` does not exist; its content is split between
> `global-doctrine/CLAUDE.md` (all-agents) and `coordinator/snippets/em-operating-doctrine.md`
> (EM-only); see `coordinator/docs/wiki/claude-md-surfaces.md`. Floor
> invariants that exist only as prose — with no hook behind them — are NOT structurally
> guaranteed to reach a session. See
> `overriding-and-tracking-upstream.md` § Floor invariance for the full account of what does and
> doesn't hold.

## Where to start

If you haven't looked at your posture block since install, that's the natural first stop: this repo's
`.claude/em-context.md`, between the `<!-- coordinator:posture:start -->` markers. Read it, notice
anything that doesn't match how you actually want to work, and change it. That's the whole loop —
no ceremony required, just an edit and a commit like any other change to a file you own.

## Negative-spec

- This page does **not** invite hook edits, `bin/` script rewrites, or skill step-logic changes — that's
  the fork side of the Mirror-Universe boundary, named above, not encouraged here.
- Doctrine-layer self-modification does **not** mean the safety-core floor is negotiable. An overlay that
  contradicts a floor invariant is a doctrine bug to fix, not a valid customization — see
  `coordinator/docs/wiki/overriding-and-tracking-upstream.md` § Floor invariance for the
  floor-invariance guarantee (now corrected — read that section, not this page's earlier claim).
- This is not the same loop as `consumer-self-evolution-loop.md` — that page covers a downstream
  consumer's local *lesson-capture* self-improvement loop (`learn-lessons` local mode routing captured
  lessons into `state/` and `docs/wiki/`). This page covers directly hand-editing your own doctrine
  prose. The two compose (a captured lesson can itself motivate a doctrine edit) but are distinct
  mechanisms.

## Related

- `.claude/em-context.md` (per repo) § Posture — the posture anchor and where the active posture is
  recorded; `~/.claude/coordinator-identity.yaml` — where the chosen anchor persists per-machine,
  across repos.
- `coordinator/docs/wiki/overriding-and-tracking-upstream.md` § Floor invariance — the
  floor-invariance guarantee.
- `coordinator/templates/postures/{precision,default,substrate-free}.md` — the pre-authored posture
  seeds the installer offers; each is a starting point, not a ceiling. They are deliberately terse:
  each renders into `.claude/em-context.md`, an *injected* boot-payload leg under a hard
  delivered-bytes ceiling, so an anchor buys its bytes against every session's context window.
- `coordinator/docs/wiki/posture-anchors.md` — the anchors' full text and the reasoning behind each
  clause. This is where to read before choosing or adapting one; the seed files carry only the gist,
  because a reader choosing a posture can follow a link and a booting EM cannot.
- claude-klabauter `coordinator/bin/render-posture-overlay.py` — the mechanism that materializes a chosen posture into
  `.claude/em-context.md`, in the repo you install from, as a managed, swappable section (re-run to
  change anchors; hand-edit the markers' contents any time in between).
- `coordinator/docs/wiki/getting-started.md` Movement 2 — the conversational, EM-facilitated path to the
  same editable surface, including the Tier-1/Tier-2 framing this page's boundary section restates.
- `coordinator/docs/wiki/eager-agent-calibration.md` — the design-as-offers ethos this page is written
  in: lead with the better alternative, never a nag.
- `coordinator/docs/wiki/overriding-and-tracking-upstream.md` — the layer-composition mechanics behind
  the floor-invariance guarantee named above (now corrected — read § Floor invariance there): how your
  personal file loads alongside, not into, the resolved plugin surface.
- `coordinator/docs/wiki/claude-md-delivery-topology.md` — the authoritative account of what
  `coordinator/CLAUDE.md` actually reaches (not fleet-wide, not always-on); read this before trusting
  any floor-invariance claim elsewhere in this page.
