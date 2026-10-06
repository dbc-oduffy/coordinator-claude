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
rescue-needed.** The terminal judge is the only legitimate end of a run. A run never stops to obtain the PM's own words: every exit-criterion, scope or mode ruling goes to `coordinator:apm` (below). Any other halt (gate
refusal, blitz refusal, a DR awaiting acceptance, or a hand-dispatched row) breaks this command, not a touchpoint to work through. When it happens, stop,
report the halt as a defect, and never finish the work by hand-dispatching rows.

**On return the EM commits, in the turn the return arrives.** The Workflow returns `next_action` and never commits: run
`coordinator-invoke dispatch.terminal_commit` with its `params`, then read the receipt. A run killed
by a usage limit still shows as running: `TaskStop` it, then `Workflow({ scriptPath, resumeFromRunId })`
once the limit resets; a dead run is committed by that op with its `script_path`.

**Cross-repo deliverables.** Each row writes in the repo its path names, and
`dispatch.terminal_commit` lands one scoped commit per repo (`sibling_commits`). Cloud
(`CLAUDE_CODE_REMOTE=true`) proceeds without asking. On a local box the emit halts at
`approve_cross_repo_write` naming the sibling repos: ask the PM; on approval re-emit with
`--cross-repo-approved` (this session's cross-repo commit assent). Never refuse a cross-repo ask
outright. A write outside every git checkout is refused at emit. A row with an `external_gate` is
withheld and listed as incomplete at `dispatch.terminal_commit`.

## Argument

- **A sizing path** (`state/sizings/<id>.yaml`, accepted: `exit_criterion.accepted` present) — go to
  *Fire*.
- **A raw ask** — run `emit-dispatch-workflow --ask "<raw ask>"` (CLI resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`) and fire the one printed
  `Workflow({ scriptPath })` line in this session. That one Workflow sizes, gates and stages the
  work. A route the sizing gate refuses (`shape`, `roadmap`, `pm-decision`) is relayed with the room it
  names; a `pm-decision` goes to `coordinator:apm` first.

## Fire

Run `emit-dispatch-workflow --sizing <sizing path>` (resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`), then fire each printed `Workflow({ scriptPath })` line in this session. Never pass `--fire`: it
spawns a headless `claude -p` child, which the foreign-emission guard refuses and which runs
without this session's roster. `--fire` is for headless and cron callers only.

- **XS** — also pass `--writes <path>` once per file the work writes (a sizing carries no footprint)
  and `--out scratch/warp/<sizing-stem>.workflow.mjs`. The op mints a one-row spine and
  re-enters the plan route.
- **S** — pass `--out` as for XS. One Workflow composes plan-agent, execute, review wave and
  `dispatch.terminal_commit`.
- **M and up** — the op delegates to `emit-wave-fire --from-sizing`. The reply carries `batons` and
  `uncommitted` (a `[baton, sizing]` pair). The minted baton is a skeleton holding only the sizing's
  intent: fill its Specification, Reference materials and Acceptance criteria, then commit exactly
  those paths, explicit pathspec, before the run proceeds.

Warp consumes the baton without a prior lobby emission: it mints or reuses the baton and emits and fires its own script.

Fan-out past ~50 agents needs a costed 2-13 agent slice first: `coordinator/docs/wiki/dispatching-parallel-agents/costed-slice-before-fan-out.md`.

Every route ends in `dispatch.terminal_commit`. `--sizing` is exclusive of `--plan`, `--inventory`
and `--queue`.

Fire in the same turn, as an in-session Workflow, and end the turn. Where the engine places a touchpoint, by interaction mode, is
`coordinator/contract/warp-touchpoints-fragment.json`; read it, never restate it. An accepted sizing
has passed every `after:sizing` touchpoint, so the run starts at `plan`.

## Touchpoints

A warp run is `ceo` mode, never hands-on. At any touchpoint that asks for the PM's words (an exit
criterion, a scope clarification, a mode), dispatch `coordinator:apm` with the question, record its
ruling where the PM quote would go, labelled `APM ruling`, never as PM words, and resume this
command on the now-accepted sizing in the same turn. Gates that stay with the PM: merge to main,
publish, cross-repo commit.

A refusal names every missing field once. Relay it verbatim; never work around it by hand-running
the stages. The closing report reads the run's completion receipt.
