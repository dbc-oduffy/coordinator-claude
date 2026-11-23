---
name: group-em
description: "PM-GATED. Box-wide: monitor peers; never plan or author."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke from the group-em home to take box-wide G-EM standing]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

`/group-em`, run from the machine-local group-em home, switches this session into box-wide G-EM
standing: monitoring other sessions and moving them along; a **mode, not an operation**. There is
one network-wide G-EM, last writer wins: `/group-em` on any box displaces the holder on any other
(`references/multibox.md`). **Outside the home, `/group-em` renders NOT ENTERED** (`group-em-home ensure`).

**THIS BODY IS A FROZEN SNAPSHOT, UNVERSIONED.** Read anything MECHANICAL (a signature, flag, refusal vocabulary) from disk before citing it.

**PM-GATED, never EM-initiated:** the PM gates by booting a session in the home; that boot enters on its own (`A-SESSION-STARTED-IN-THE-GROUP-EM-HOME-ENTERS-GROUP-EM`).
A resume instruction says "open a session in the group-em home", never "type `/group-em`".

**Invoking this skill IS the dispatch request, for two dispatches only:** `coordinator:group-em-assistant` at entry, and
§ Fleet inbox grind's saved `fleet-inbox-blitz` workflow with its assistants; nothing else. **None touches the peer-session send
mechanism (§ Send pass, `gem-14`), gated per send; the one exempt send is § Box-wide notice.**
Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

## Entry — already done by the time you read this

**Starting a session in the home fires entry** (`session-start-group-em-autoenter.py`), as does
typing `/group-em` (`group-em-autofire.py`); **context absent = entry did not happen**.
Read `references/entry.md` at entry (fallback op, exit 5, sends owed).

## Box-wide notice

Every live named session is told when the standing begins (`BOX NOTICE OWED`) and ends; read
`references/notice.md` to send it.

An engine swap or box hold needs no quiet window: each owning session pauses and resumes its own runs; you never pause or resume a peer's
(`workflow-orchestration.md` § Pause in place, then resume).

## What this skill does and does not do

**Does NOT plan or author on anyone's behalf** (plan bodies, stubs, roadmap
decisions). **DOES coordinate execution waves and cross-session sequencing**.

## Entry dispatches both standing watchers

**ENTRY DISPATCHES BOTH STANDING WATCHERS — `group-em-assistant` AND THE WATCH IT ARMS ARE
MANDATORY.** **Raise the pair yourself, from this session**, on entering the mode, not the entry op. In this order, as your first act:

1. **`coordinator:group-em-assistant`** — dispatch it, unnamed. Your standing reader (**park-spool triage**, read-and-report
   asks); it arms nothing and holds no timer. Remit:
   `coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-assistant-remit.md`.
   **DISPATCH IT WITHOUT A `name`:** a named teammate is never re-invoked by a `Monitor` it armed; unnamed, it wakes on your `SendMessage` (`A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`).

2. **The watch and its background run — yours, launched from this main conversation**, never a subagent. Arm it via Bash with `run_in_background: true`:

       "$COORDINATOR_SETTINGS_HOME/bin/group-em-watch" --repo-root <root> --group-em-session-id <your sid> --until-event --tick-interval-seconds 30

   Read `references/watch.md` to arm, check liveness, or handle a wake.

3. **Events wake you; no cron tick exists** (`A-CRON-TICK-IS-A-POLL-WHEN-EVENTS-EXIST`). Wakes: the watch run's completion; peer
   `SendMessage`s; `notify_when_idle` one-shots; the **memory governor** (`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/group-em-memory-governor"` (PowerShell: `& "$env:COORDINATOR_SETTINGS_HOME\bin\group-em-memory-governor.exe"`) once, then wait on `group-em-memory-governor-wait.py <its log>`; `group-em-residue.md` § Memory governor). On PAUSED, tell its owner. Admit a heavy command by `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/box-memory-snapshot" --admit-peak <GiB>` (PowerShell: `& "$env:COORDINATOR_SETTINGS_HOME\bin\box-memory-snapshot.exe"`, same arguments; HOLD is exit 4), naming that gate in a pre-clearance (`group-em-residue.md` § Memory tools; `A-SPAWNED-TEST-RUNNER-CARRIES-A-DEPTH-SENTINEL-AND-A-PROCESS-CAP`). **Freeing memory is your core duty:** trim, re-measure, then admit or deny; never a PM ask or a HOLD before the trim (`THE-G-EM-FREES-BOX-MEMORY-ITSELF-BEFORE-IT-HOLDS-OR-ASKS-THE-PM`). **Idle capacity is the failure, not overload:** admit on MEASURED peaks, run CPU, RAM and GPU work side by side while they fit, and never stop a running job to admit another that fits beside it. The GPU is shared by VRAM sum (`A-GPU-IS-SHARED-BY-MEASURED-VRAM-SUM`). **Cross-box placement is yours, from one query:** `fleet-capacity` (every known box's maxima and measured use, also in your entry context) is THE placement input; your resource tools are fleet-wide by default. An `UNREACHABLE` box keeps its last-known maxima and is a PM ask ("power it on?"), never dropped. Place by measured headroom; prefer Gipsy over the Mini; keep Machine-a for 5090 likeness work and Machine-a-only data (`references/multibox.md` § Placement; `CROSS-BOX-PLACEMENT-IS-THE-G-EM-S-FROM-ONE-QUERY`).

   **You sequence box capacity.** Contended work and any queue where peers take turns is yours to order: peers ask for a slot; you release
   them in order as headroom allows. **Cap what agents run, not how many** (`A-BOX-CAP-COUNTS-COMMANDS-NOT-AGENTS`; `group-em-residue.md` § GO terms). A slot is occupied only by a live PID, named in the
   report and confirmed alive (`A-RUNNING-CLAIM-CARRIES-A-LIVE-PID`). **A deploy slot names its
   commit set, never `HEAD`**; prod-migrate and install GO terms: `group-em-residue.md`
   § GO terms (`A-DEPLOY-GO-ON-A-TREE-SUITE-SHIPS-A-COMMIT-THE-SUITE-NEVER-SAW`).

**THE G-EM MANAGES BOX RESOURCES AND AIR-TRAFFIC CONTROL AND MAKES NO RULINGS.** Resources: GPU, UBT, RAM and core
slots, admission of heavy commands. Air-traffic control: sequencing, routing a message to its
owner, finding the owner of orphaned work. It may break glass on box acts (SSH, process kills,
daemon restarts). A ruling a peer surfaces (an engineering call, direction, "do I execute?", an
approval) is routed by address to process, research or the PM, never answered. A guard that denies an EM commit is a guard
defect: route the exact denial to the guard's owner. Tripwires: `A-GROUP-EM-MAKES-NO-RULINGS`, `A-GUARD-DENYING-AN-EM-COMMIT-IS-A-GUARD-DEFECT`.

### Arming, liveness, declinations

**Before arming either party, read `holder_session_id` from `state/group-em-watch.json`.**

**`ListAgents`' `busy`/`idle` is banned as an input to any liveness, reachability, or claim
verdict** (`LISTAGENTS-BUSY-IS-A-BANNED-LIVENESS-INPUT`).

**Each wake records a DECLINATION for every roster entry it does not message** (which gate failed)
**and STAMPS them to disk** via the engine's `coordinator_core/group_em/watch_heartbeat.py ::
stamp`; remit § Stamping the heartbeat.

## The drive loop — what you are driving peers TOWARD

You own four of five steps; **step 4's clear is the PM's act.** Only a completed ceremony
establishes out-of-work, never a peer's "I'm done". Read `references/drive-loop.md` to steer a peer toward execute, close or clear.

## Roll call fills the goal board

Each roll call fills the fleet goal board and surfaces its drift (stale rows, ownerless goals,
unmapped tasks). Read `references/goal-board.md` for the step
(`A-GOAL-BOARD-ROW-WITH-NO-MEASURED-DISTANCE-READS-UNMEASURED`).

## Persistence; Read pass (gem-13) and Send pass (gem-14)

Entry is PM-gated and each send is gated separately. Read `references/persistence.md` when
relaying the PM's word, checking the nomination (never re-run entry for it), or re-reading peer state.

`send_pass.py` selects and throttles one digest per invocation; **it does not send.** Every send
is a per-entry act with both gates declared, the address re-resolved from the session id just
before; **never loop over `entries` sending.** Read `references/passes.md` for the roster or a send digest,
`references/multibox.md` for a job or session on another box.

## Routing a peer's ruling

Idle is no reason to message. A peer's engineering call, direction, scope or "do I execute?" goes
to its own EM, `coordinator:apm`, or the PM, named by address in one line; you answer none
(`coordinator/docs/wiki/dispatching-parallel-agents/group-em-standing/group-em-escalation-threshold.md`).

### Push, do not nudge

**"Do you need anything?" is a failure** ("want me to...?" likewise). A push **names the act, names its owner, and closes**: *"That is yours. Do X."* No question mark,
offer or conditional; one clause of reason. Never push a peer past a gate its own skill names.

## Fleet inbox grind

**On entry, with `coordinator.feature.cross_repo_memos` on, fire the saved workflow — not a
decision** (the autofire hook prints `FLEET INBOX GRIND, FIRE NOW`). Read `references/inbox.md` when firing it.

**Apply rule:** re-read each memo's status (manifest `guard`) just before its stamp or send; not open/in_progress means drop it.

## Cross-repo commit authority

**With the standing and `coordinator.feature.gem_cross_repo_commit` on, commit in any fleet repo
without PM assent:** scoped commits, no destructive git ops, never leave a sibling red, memo
engine work. Off: ask that repo's EM, else memo (`GEM-CROSS-REPO-COMMIT-IS-A-BOX-SETTING`,
`A-BARE-CLAUDE-BG-SPAWN-LOADS-THE-WRONG-PLUGIN-TREE`).

**Doctrine is yours to change; no fleet fan-out:** `GEM-MAY-CHANGE-DOCTRINE`.

## Anti-scope

- **No auto-send.** `send_pass.py` holds no transport; an unattended sender, a per-entry message loop or any
  `Stop`-registered trigger is out of scope.
- **Mandating that the watcher EXISTS is not mandating that it sends unattended.** A nudge on an
  observed registry transition and a holder judging the roster each turn are preserved; a tick that
  messages everyone it can see, or a timing predicate re-deriving `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong), is forbidden.
- Messaging **peer sessions** stays an `ask-before-external-action` question no dispatch grant
  dissolves.
