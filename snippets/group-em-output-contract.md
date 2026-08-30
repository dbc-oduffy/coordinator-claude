<!-- canonical source for group-em-output-contract — edit here. Read from one place only
     (coordinator/skills/workstream-complete/SKILL.md § Final Summary); not registered in
     registry.toml, per that file's own header comment on paste-governed vs read-from-one-place
     snippets — this one is the latter. -->
<!-- consumers: coordinator/skills/workstream-complete/SKILL.md (pointer, not paste) -->

# Group EM Human-Channel Output Contract

Governs what a session holding the Group EM role may emit to the PM's window. Scope: production,
not formatting — see § Filter at source.

## The permitted emission

Exactly one form reaches the PM's window: **a decision awaiting them.** Three fields, from the
gem-01 research corpus's Core Output Contract (`state/roadmap/gem-01/research-corpus/
supervisor-facing-agent-output.md` § What This Suggests for a Mechanism):

1. **The decision point** — one sentence: what cannot be resolved without them.
2. **The action required** — approve / choose / provide input / override.
3. **The address** — when the decision is live in another session, the resolved peer address
   (never a relay of that session's state). See `coordinator/docs/wiki/
   group-em-escalation-threshold.md` § Point for the resolution route.

## Excluded classes

Named so they cannot be re-entered under another label:

- Reasoning and rationale.
- Working status and intermediate steps.
- Peer-session state and commit hashes relayed rather than pointed at.
- Metrics and logs.
- **Offers, FYIs, "worth your eye", and self-labelled-non-blocking questions.** A non-blocking
  label does not exempt an emission — it spends the PM's attention identically to a blocking ask.
  "One ask per turn" is a cap on blocking asks, never an allowance to spend attention on anything
  else.

## Filter at source, not at the end

The narration must not be produced, not merely relegated. Appending a summary to unchanged
narration fails this contract — a summary tacked onto a wall of reasoning is still a wall of
reasoning the PM has to read past. The alerting literature converges on this: presentational
fixes fail, and verbosity measurably impairs human decision speed (SRE/clinical alarm-fatigue
literature — 72-99% of clinical alarms are non-actionable and desensitize responders to the
genuine ones; `supervisor-facing-agent-output.md` § Question 2, § Question 5).

## Boundary with first-officer-posture C5

The first-officer-posture plan's chunk C5 owns the **ask-doctrine** — when an EM may ask at all,
and removal of its exemptions — in the global doctrine's `CLAUDE.md` and
`coordinator/snippets/em-operating-doctrine.md`. This contract does not modify either file. This
contract owns what a **coordinating** session may **emit**, ask or not — the shape of the
channel, not the threshold for using it.

## The falsifier

*A PM reading one screen of a coordinating session's output can name every decision awaiting
them, and nothing else appears.*
