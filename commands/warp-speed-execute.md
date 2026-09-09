---
name: warp-speed-execute
description: "The wide run. Forwards to /mise-en-place, which carries the same ceremony's body."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "[baton-path [AND baton-path]...] [--hibernate]"
---

# Warp-Speed-Execute

The run named `warp-speed-execute` is `/mise-en-place`'s run. There is one wide-run ceremony, not
two: certification entry, aggregate baton, Kira waves, subtractive adjudication and the exit-side
orphan check are all phases of it.

**Read `${CLAUDE_PLUGIN_ROOT}/commands/mise-en-place.md` and run it end to end.** Nothing in this
file overrides a phase there.

## Either verb is a first-class invocation

Both autofire hooks match this verb as well as `mise-en-place` —
`hooks/scripts/mise-autofire.py :: _MISE_COMMAND_NAMES` mints the Phase 1 run-id and briefs it,
`hooks/scripts/pickup-autofire.py :: _BATON_GRAB_COMMAND_NAMES` claims the batons Phase 0a expects
to be already claimed. Invoked by either name the run starts with the same inputs. There is no
manual step.

Engine vocabulary does not follow the verb: the sentinel mode, the cadence passed to
`mint-run-id`/`brief` (`mise-autofire.py :: _CADENCE`), the run-id family and
`handoff.schema.json`'s cadence key all spell it `mise-en-place`. A verb added to either frozenset
is added to both, or the run starts half-wired and both hooks report success.
