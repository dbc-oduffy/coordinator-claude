---
name: roadmap-blitz
description: "PM-GATED. Turns a sizing with xl_exit: roadmap into staged roadmap batons in one background wave, with one Approve gate, then hands them to plan-blitz."
description-budget: 320
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "Workflow", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[--sizing <path>] --interaction-mode hands-on|pm|ceo"
---

# Roadmap-blitz — an XL sizing to roadmap batons, one approval

Batches `coordinator:roadmap-planning` for a sizing with `xl_exit: roadmap`: the workflow
inventories, clusters, substantiates, reviews, and drafts OVERVIEW; one Approve gate stands in for
the PM rounds; then `roadmap.blitz_stage` freezes a gate report and stub batons. Rationale: wiki
`planning/roadmap-blitz`. The wave fires from the top-level EM only — a dispatched agent cannot
fan out (`A-SKILL-PHASE-NAMES-ITS-ACTOR`).

**When NOT to use:** PM present → `coordinator:roadmap-planning`; one feature →
`coordinator:plan`; goals not ratified → `coordinator:goal-blitz`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

**Host shapes.** Calls are Shape W; on POSIX run `coordinator-invoke <op> '<json>'` (Shape B).

---

## The flow

**This runs at Sonnet;** Opus judgment happens INSIDE the workflow. Args and result shapes are pinned by `${CLAUDE_PLUGIN_ROOT}/skills/roadmap-blitz/roadmap-blitz-contract.json`.

### 0. Preflight

Resolve the launcher per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; unresolved —
**stop and report**, never fabricate a fire or result. Confirm the sizing exists. Trail:
`state/scratch/roadmap-blitz/<run-id>/`.

### 1. Emit the fire — never hand-write the args

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/roadmap-blitz/emit-roadmap-fire.py" \
        --repo-root <abs> --trail-dir <abs repo>/state/scratch/roadmap-blitz \
        --provision-sidecar-cli <abs provision-sidecar> [--sizing <path>] --interaction-mode <mode>

`--provision-sidecar-cli` is the `provision-sidecar` CLI (basename checked; never `coordinator-invoke`), resolved per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. `--interaction-mode` is required unless the sizing carries `interaction_mode:`; the emitter refuses (exit 2) otherwise, so pass the mode `sizing-assemble` reported.

Targeted with `--sizing`, else a sweep of sizings with `xl_exit: roadmap`, `status: routed` and no
`state/roadmap/<run-id>/` yet. It freezes `<trail>/candidates.json`, binds the args via
`workflow.bind_args` into `<trail>/roadmap-blitz.fire.mjs`, and prints one `Workflow({ scriptPath })`
line per sizing. Pass `--no-plugin-agents` where `coordinator:*` types do not resolve. Nothing to
emit or a nonzero exit: report stderr and stop.

- **Never hand-type an args object.** Tripwire: `A-HAND-TYPED-WAVE-ARG-IS-AN-UNARCHIVED-FIRE`.
- **An emitted fire is a SNAPSHOT — RE-EMIT, never re-fire as found** after a workflow fix.
- **Resolve `${CLAUDE_PLUGIN_ROOT}`; never pass a repo-relative path** to a workflow: the emitter
  binds it as `pluginRoot` (`--plugin-root` overrides); a consumer repo has no `coordinator/` directory.

### 2. Fire and wait

Fire the printed line, wait, and do not read the trail mid-wave. Read the result's `awaitingApproval`,
`gate_report_path` and `incidents`.

### 3. Approve — hands-on only

With `interactionMode: hands-on` the PM approves: the run returns `awaitingApproval: true` and a
null `gate_report_path`. Ask once with `AskUserQuestion` over `state/roadmap/<run-id>/OVERVIEW.md`
(approve or decline, plus the PM's words), then write the answer
**verbatim** to `<trail>/approval.json`, shaped `{verdict, approver: "pm", utterance, recorded_at}`
(`verdict` is `approved` or `declined`). Never infer, backfill or paraphrase an approval; a picker
label is EM text, so record `"<label> (option picked)"` plus any PM words. `declined` ends the
run. The resume stamps `approver: pm` and `approval_utterance` onto OVERVIEW.md, where plan
authors read the Approve. Then:

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/roadmap-blitz/emit-roadmap-fire.py" \
        --repo-root <abs> --resume --trail-dir <abs trail>

and fire the printed line. It refuses an absent or non-`pm` `approval.json`; never route around a
refusal. In `pm` or `ceo` mode the workflow's APM approves inside the run: no resume.

### 4. Hand to plan-blitz

On a returned `gate_report_path`, invoke `coordinator:plan-blitz` with that report and nothing
else to decide. A null `gate_report_path` with `incidents`: report them and stop.

### 5. Surface owedRetirements

List the result's `owedRetirements` (live source plans the roadmap supersedes) to the PM; retiring
one (roadmap-planning Step 2.9) is the PM's call, never made here.

---

## Rules

**Review fires unconditionally; the Approve gate is the only gate.** Tripwire: `A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ`.

**One fire binds one sizing;** a sweep yields one fire per candidate.

**clusters.md carries a `Stub slug prefix:` line**, a short word never date-led, or two roadmaps collide on stub ids.

**Cross-plan seams are owned by plan-blitz's readiness gate:** an export one plan needs from an
earlier plan, or a declared-write collision between sibling plans, is checked there.

**Never write `state/roadmap/` by hand** — the workflow and `roadmap.blitz_stage` are the only writers.

---

## Anti-scope

- Does not edit `roadmap-planning`, approve for the PM, change the workflow's effort pins, or
  execute plans (`coordinator:plan-blitz` and warp's roadmap arm own what follows).
