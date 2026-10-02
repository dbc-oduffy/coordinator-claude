---
name: fire-and-forget
description: "\"fire and forget\" / \"fire and forget\": a raw ask or sizing to a reviewed commit in one fire."
allowed-tools: ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "Agent", "Skill"]
argument-hint: "<raw ask | state/sizings/<id>.yaml>"
---

# Warp-Speed-Execute

Fire-and-forget: one invocation takes an accepted sizing to a reviewed terminal commit. It is its
own ceremony; it forwards to no other command and no autofire hook matches it. The engine emits the
chained Workflow (`emit-dispatch-workflow --sizing`); this body runs that op once and fires the
result.

**Contract: one Workflow, start to finish. The EM is idle until the run reports completion or
rescue-needed.** Past the mode's own touchpoints (below), the terminal judge is the only legitimate end of a run. Any other halt (gate
refusal, blitz refusal, an external-gate row, a DR awaiting acceptance, or a hand-dispatched or
hand-committed row) breaks this command, not a touchpoint to work through. When it happens, stop,
report the halt as a defect, and never finish the work by hand-dispatching rows.

**Refuse cross-repo deliverables.** If the ask or sizing names a sibling repo as a write target, or the
emitted plan carries any `external_gate: commit-in-owner-repo` row, refuse before firing. Say:
"warp cannot carry a cross-repo deliverable yet; route via `coordinator:plan` and
`/execute-plan`". The run pins to one repo root, and the engine drops sibling-repo rows without
reporting them.

## Argument

- **A sizing path** (`state/sizings/<id>.yaml`, accepted: `exit_criterion.accepted` present) — go to
  *Fire*.
- **A raw ask** — run `emit-dispatch-workflow --ask "<raw ask>"` (CLI resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`) and fire the one printed
  `Workflow({ scriptPath })` line in this session. That one Workflow sizes, gates and stages the
  work, and the run returns next_action `dispatch.terminal_commit`. Never pass `--fire`; never run
  it headless. A route the sizing gate refuses (`shape`, `roadmap`, `pm-decision`) is relayed to the
  PM with the room it names. Do not size by hand.

## Fire

Run `emit-dispatch-workflow --sizing <sizing path>` (resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`), then fire each printed `Workflow({ scriptPath })` line in this session. Never pass `--fire`: it
spawns a headless `claude -p` child, which the foreign-emission guard refuses and which runs
without this session's roster. `--fire` is for headless and cron callers only.

- **XS** — also pass `--writes <path>` once per file the work writes (a sizing carries no footprint)
  and `--out state/scratch/warp/<sizing-stem>.workflow.mjs`. The op mints a one-row spine and
  re-enters the plan route.
- **S** — pass `--out` as for XS. One Workflow composes plan-agent, execute, review wave and
  `dispatch.terminal_commit`.
- **M and up** — the op delegates to `emit-wave-fire --from-sizing`; pass `--trail-dir <dir>` only
  to name the trail. The reply carries `batons` and `uncommitted` (a `[baton, sizing]` pair): commit
  exactly those paths, explicit pathspec, before the run proceeds.

Every route ends in `dispatch.terminal_commit`. `--sizing` is exclusive of `--plan`, `--inventory`
and `--queue`.

Fire in the same turn, as an in-session Workflow, and end the turn. Where a run halts, by interaction mode, is
`coordinator/contract/warp-touchpoints-fragment.json`; read it, never restate it. An accepted sizing
has passed every `after:sizing` touchpoint, so the run starts at `plan`. At a halting touchpoint the
run writes its state and stops; the resume is this command on the now-accepted sizing.

A refusal names every missing field once. Relay it verbatim; never work around it by hand-running
the stages. The closing report reads the run's completion receipt.
