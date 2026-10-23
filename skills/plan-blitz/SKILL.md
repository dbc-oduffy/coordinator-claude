---
name: plan-blitz
description: "PM-GATED. Plan every baton lacking an approved plan, in scout/EM/planner waves. Or named batons."
description-budget: 320
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "Workflow", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[<baton-id> ...] [--roadmap-id <id>] [--waves <n>] [--dry-run]"
---

# Plan-blitz — a roadmap's worth of plans, in waves

Plans an existing roadmap, N batons per wave. Waves fire from the top-level EM only (`A-SKILL-PHASE-NAMES-ITS-ACTOR`).

---

## Two modes

| Mode | Target set |
|---|---|
| **Sweep** (default, no args) | every baton the engine returns as `needs_plan` — no linked plan, or one not yet review-cleared. `--roadmap-id` narrows to one roadmap. |
| **Targeted** (`<baton-id> ...`) | the ids you pass as `targets`; everything unnamed stays a fully-resolved BLOCKER, not a candidate. |

**Check `unmatched_targets` on every targeted run.**

**When NOT to use:** no roadmap → `coordinator:roadmap-planning`. One baton → `coordinator:sizing`,
then `coordinator:plan`. Plans to execute → `coordinator:execute-plan`. Bugs → `coordinator:bug-blitz`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

Calls below are Shape W; on POSIX run `coordinator-invoke <op> '<json>'` (Shape B).

---

## The two gates — read them, never derive them

One `blocked_by` edge, two questions. **Planning** may start when every blocker is coded *or*
carries a review-approved plan. **Execution** may start only when every blocker is coded. Tripwire:
`A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.

Both come off one disk-reading op; **never hand-derive either from `blocked_by`.**

Invoke `coordinator-invoke` per the ladder in `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`
— rung 0 (Shape W, the `.exe` launcher) on a PowerShell host:

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.plan_gate '{"roadmap_id":"<id>"}'`

---

## The flow — a loop with no judgment in it

**This runs at Sonnet.** Opus judgment happens INSIDE a wave.

### 0. Preflight — confirm the engine is reachable

Resolve the launcher per `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`. Unresolved:
**stop and report**; never enter `roadmap.plan_gate`, `roadmap.blitz_land` or a dispatch.

### 1. Read the gate

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.plan_gate '{}'`

| Field | If non-empty | Response |
|---|---|---|
| `unresolved_blockers` | an edge names no record on disk | Stop ONLY for a wave member about to fire; else report and proceed (the gate fails that baton CLOSED). |
| `cycles` | batons block each other | Stop and report the named members. |
| `counts.unschedulable` | blockers this pass cannot clear | Proceed; excluded by design. |

**A blocker naming a peer EM role is the standing case; never delete the edge** — it
clears when the peer answers. **An edge is a DISCOVERED dependency, never a way to suppress a candidate.**

**Suppression is a HOLD: three flat baton keys the gate reads —
`plan_blitz_hold_reason`, `plan_blitz_hold_cite`, `plan_blitz_hold_until`.** The gate sets
`candidate: false` and reports the baton under `held`. **A hold with no reason is ignored.**
**`plan_blitz_hold_cleared_by` (the clearing commit) lifts a hold; the baton is offered again.**
**`external_gate` on a BATON record does nothing** (real on PLAN SPINE ROWS only).

### 2. Scaffold the trail and freeze the gate

`state/plan-blitz/<run-id>/wave-<N>.gate-report.json`, `<run-id>` being this run's UTC start as
`YYYYMMDDTHHMMSSZ`. Scaffold the directory first.

- **One report PER WAVE**, frozen after the previous wave landed.
- **Pass `--bare`** (`result` alone). Tripwire: `AN-ENVELOPE-FROZEN-AS-A-GATE-REPORT-READS-AS-AN-EMPTY-WAVE`.
- **Freeze by redirection** (`1> gate-report.json 2> gate.stderr`); read `utf-8-sig`.

### 2a. Check the wave for finished work

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/recycle-check.py" --repo-root <repo> \
        --gate-report <the frozen report> --exclude-run <this run-id>

`RECYCLED` (exit 1): re-run that landing with the SHA; never drop the baton by hand.
`RESURRECTED` (exit 1): remove or re-archive the live copy. Tripwire: `A-FINISHED-BATON-THE-LANDING-NEVER-STAMPED-COMES-BACK-AS-A-CANDIDATE`.

### 3. Fire the wave — emit it; never hand-write the args

    "$COORDINATOR_SETTINGS_HOME/bin/emit-wave-fire" \
        --repo-root <abs> --trail-dir <abs> --wave-index N --wave-number N \
        --gate-report <trail-dir>/wave-N.gate-report.json

It derives every per-baton field from the frozen report, and prints
one `Workflow({ scriptPath })` line per fire; fire each. Pass `--plugin-agents-available true`
where `coordinator:*` types resolve. `workflows/plan-blitz.mjs` holds the args contract.

- **Never hand-type an args object.** Tripwire: `A-HAND-TYPED-WAVE-ARG-IS-AN-UNARCHIVED-FIRE`.
- **An emitted fire is a SNAPSHOT — RE-EMIT after any workflow fix.** Never retro-patch a fire that ran.
- **`--wave-number` is this wave's absolute label**; else `--wave-index`.
- **At most 8 batons per fire**; the emitter splits a larger wave, sharing the `waveIndex`.
- **`--exclude <baton-id>` narrows what is FIRED, never what the gate computed.**
- **Search the trail RECURSIVELY; order slots by INTEGER wave index.**

**Fires may run CONCURRENTLY; the driver owns disjointness.**

- **Subtract your in-flight set from every fresh gate read** by `planPath`, not just baton id, and adjudicated batons too — a `pulled` or `errored` baton returns at the head of the next read. Tripwire: `A-GATE-READ-DOES-NOT-KNOW-A-FIRE-IS-RUNNING`.
- **Re-freeze the gate before re-emitting a baton whose plan you edited.**
- **A hold only you remember is not a hold**: write it in `RUN-NOTES.md`.

**`emit-wave-fire` resolves `provisionSidecarCli`**; pass `--provision-sidecar-cli` only to
OVERRIDE. A findings path with no `subagent-share` segment is a REFUSAL. Tripwire: `A-SIDECAR-THE-DISPOSITION-OP-REFUSES-LOSES-ONLY-THE-RECORD`.

**A box with no install is Rung N** — pass `--engine-root` (`--live-engine-tree` where only the
authoring tree carries `workflow.bind_args`). Tripwire: `A-PUBLISHED-MIRROR-OLDER-THAN-AN-OP-REFUSES-AS-A-MISSING-ENGINE`.

Every baton carries `executionOpen` (from `execution_gate.open`; no default). **Resolve
`${CLAUDE_PLUGIN_ROOT}`; never pass a repo-relative path** to a workflow.

### 4. Run the wave's XS runs, then land — one call over every fire of the wave

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/land-wave.py" \
        --repo-root <abs> [--shipped-in <batonId>=<sha>] <fire-result.json> ...

One file per fire; pass the task output file as-is. It lands
each fire through `roadmap.blitz_land`, **sums the three lanes across every fire**, and states the
stop condition from that sum. It refuses if the fires disagree about `waveIndex`, or if a fire
carries XS and no `--shipped-in` was given. It writes and commits `wave-<n>.landing.<slot>.json`
into the trail (`--no-commit` lists them). **Never redirect its stdout onto that path.**

**Run each `xsRuns` entry before landing, one at a time** (each commits):
`& "$env:COORDINATOR_SETTINGS_HOME\bin\emit-dispatch-workflow.exe" --sizing <sizingObject> --baton <record>` (the entry's `sizingObject` and `record`; the sizing's `baton:` key names the record, and the CLI refuses a pair where neither side names the other)
(POSIX: the settings-home `bin/` ladder), fire its printed `Workflow` line, then run its
`terminal_commit_cli` line. Read `sha` and `close.kind`: expect `xs-s-run`; anything else is
reported, not landed around. Pass `--shipped-in <batonId>=<sha>` per run. Never hand-commit XS work:
`A-HAND-COMMITTED-XS-RUN-LANDS-WITHOUT-A-CLOSE-BLOCK`. `close_dispatched` stamps `shipped` with that `shipped_in`.

`--errored-only <fire result>` re-lands `errored` entries (the op only; never re-fire them).
`roadmap.blitz_land` mints a baton per `replan` and returns `next_wave`.

**Three lanes land differently; the op picks by route.**

| Route | Size | What landing does |
|---|---|---|
| `plan` | M / L | link the plan to its baton, then stamp `approved` |
| `spec-dispatch` | S | park the spec onto the baton, stamp execution-ready (`execution_authorized_*` + `handoff_phase: execution`) |
| `dispatch` | XS | the driver's XS ask run does the work; landing stamps `shipped` with its terminal_commit SHA |

An S plan stays `draft` by design (`needs_plan` keys off the execution stamp). **Never hand-stamp `status: approved`.**

**Read `refused[]` on every landing**; never route around one.

### 5. Loop

**`--waves` runs until `next_wave.batons` is empty.** Fire `next_wave`, land it, repeat, under the stop conditions below.
A single wave is the opt-in: `--waves 1` stops after wave 0 lands and reports a non-empty `next_wave.batons` as remaining work. `--waves <n>` caps the run at `n`. Tripwire: `A-MULTI-WAVE-BLITZ-IS-NOT-THE-DEFAULT`.

**Stop conditions, all mechanical:**

- `next_wave.batons` is empty.
- `--waves` exhausted.
- A wave lands zero `approved`, `execution_ready` and `closed` — it opened nothing. Report and stop.
  **Zero `approved` alone is not the test:** an all-S ready set approves nothing and still advances
  (§ Three lanes). Tripwire: `AN-ALL-S-WAVE-APPROVES-NOTHING-AND-STILL-ADVANCES`.
  **A WAVE-level test:** sum the three lanes across every fire at this `waveIndex`.
  **Only a FINISHED wave counts** — check completion BEFORE reading the lanes. **Never land an unfinished fire**; resume it, or re-emit and re-fire,
  closing a finished XS with `archive-stamp-cli ship-handoff <path> --sha <sha> --archive`. Tripwire:
  `AN-UNFINISHED-WAVE-IS-NOT-A-WAVE-THAT-OPENED-NOTHING`.
- The usage-limit advisory has fired — fire no further wave; land the current wave through step 4,
  then report and stop with the reset time (`coordinator/docs/wiki/skills-corpus/usage-limit-pause.md`); tripwire:
  `A-DRIVER-PAST-ITS-USAGE-THRESHOLD-FIRES-NOTHING-NEW`.
- `refused[]` is non-empty — report and stop.
- `land-wave` exits 4 (still `errored`) — report each `opError` verbatim, stop.
- `surfacedToPm` is non-empty — each is `pm_only`; **never re-queue one.** `adjudicated` entries are APM-closed and never PM-facing; only `surfacedToPm` reaches the PM. Report `adjudicated` by count.

The driver escalates rather than decides: an unresolved blocker, a cycle, a `refused` entry, `surfacedToPm` residue, an empty wave.

---

## Rules that hold across every wave

**Review fires unconditionally; the EM gates once, at the end.** Tripwire: `A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ`.

**Host availability on the wave's box is never a pull reason:** a plan with rows behind a declared `external_gate` is READY (a schedule fact). Tripwires: `A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`,
`THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON`.

**One reviewer-attributed option is a recommendation, not a dead end;** contested options are arbitrated by the resolve pass. Tripwire: `A-SINGLE-REVIEWER-OPTION-IS-A-RECOMMENDATION-NOT-A-DEAD-END`.

**No reviewer is prescribed in a plan file; its `review_signals` select them** → reviewer: front-end → `senior-front-end`, data-science → `staff-data-sci`, ux-flow → `staff-ux`, cross-repo-seam → `eng-director`; added to the sized reviewers.

**The last reviewer's op verdict decides:** `judgment` with nothing blocking buys one resolver and one re-ask; a BLOCKED reviewer or failed resolve pulls, reason counting blocking vs advisory (`A-JUDGMENT-VERDICT-WITH-NO-BLOCKED-REVIEWER-IS-RESOLVED-NOT-PULLED`), a PIVOT replans, an op failure (retried once) is `errored`. The prep-gate enricher spawns only for named mechanical repairs or a lone census-unscreenable failure. `EXECUTOR_HEAVY` is repaired in-wave, never pulled: move the command to a `coordinator:test-runner` V row (`A-HEAVY-COMMAND-ON-AN-EXECUTOR-ROW-PULLS-THE-PLAN`).

**`BLOCKED` and `PIVOT` are not a severity ladder.** `BLOCKED`: the reviewer applied its
findings; the fixed plan is approved the same wave. `PIVOT`: no findings repair this direction; it
routes, never halts — a replan baton, the other N-1 plans finish, co-reviewer findings carry as
`Suspended (PIVOT)`. Tripwire: `A-BLOCKED-REVIEW-IS-NOT-A-PIVOT`.

**Never blitz a claimed or `in_flight` baton, or open a shut gate.**

**The blitz-em never rules a PM decision.** `route: pm-decision` and XL exits go to the Adjudicate
phase (APM for scope; staff-eng or a domain reviewer for code); only `pm_only` stays in `surfacedToPm`.

**`approved` is not `mise-prepped`, and a wave never stamps one.** Body edits invalidate a stamp; frontmatter writes do not. Never read `mise_prepped_by` for presence. Tripwire:
`A-PRESENT-MISE-PREPPED-STAMP-IS-NOT-A-CERTIFICATION`; consumer contract:
`coordinator/docs/wiki/lesson-triage/mise-prepped-attest.md`.

---

## Anti-scope

- Does not author roadmap batons, ratify sizings, or review code — wave reviewers review **plans**.
- Does not execute plans, and never opens an execution gate. It stops at *ready to execute*.
  Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.

