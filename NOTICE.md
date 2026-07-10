<!-- WORDING IS PM-REVIEW-GATED before this ships to consumers (v3split-02 finding #3). -->

# Notice

This release of coordinator-claude ships **doctrine**: skills, agents, reviewer personas,
and planning conventions — the thinking layer that shapes how work gets planned, reviewed,
and executed.

It does **not** yet ship the **executing machinery layer** (the `bin/`, `hooks/`, and `lib/`
scripts that skills shell out to at runtime). That layer is delivered separately, as a
follow-on release — see the project roadmap for the machinery-delivery track.

## What this means for you

Everything you'd expect from the doctrine layer works today: read the skills, study the
agent and reviewer personas, follow the planning conventions, adapt them to your own
workflow. Where a skill's steps *shell out* to a coordinator binary, that step is
**reference material — a preview of the intended workflow** — until the machinery layer
lands alongside it. Nothing here is broken; it's simply doctrine ahead of its runtime.

We'll update this notice once the machinery layer ships.
