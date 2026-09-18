---
name: plan-blitz
description: "PM-GATED. Sweep every baton in the repo that lacks an approved plan, in waves — sonnet scouts size, an Opus EM finalises, Opus planners write, plans are reviewed and integrated without the EM in the loop, and the EM gates readiness at the end. Or target named batons. Wave N+1 fires on wave N's approvals, not its landings."
description-budget: 320
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "Workflow", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[<baton-id> ...] [--roadmap-id <id>] [--waves <n>] [--dry-run] [--repair <baton-id> ...]"
---

# Plan-blitz — a roadmap's worth of plans, in waves

Consumes a roadmap that already exists and produces plans for it, N batons per wave instead of one
per session. Rationale and the measured case behind every rule below: fleet doctrine wiki under
this skill's own name — read when a rule looks wrong, never to decide whether to follow one. The
tripwires are the greppable entry points.

---

## Three modes

| Mode | Target set |
|---|---|
| **Sweep** (default, no args) | every baton the engine returns as `needs_plan` — no linked plan, or one not yet review-cleared. An approved baton is out of the set, staying in the graph only as a satisfied blocker. `--roadmap-id` narrows to one roadmap. |
| **Targeted** (`<baton-id> ...`) | the ids you pass as `targets` (a gate row's `id`, or the baton's filename stem). Everything unnamed stops being a candidate but stays a fully-resolved BLOCKER — narrowing the ask never narrows what the answer is computed from. |
| **Repair** (`--repair <baton-id> ...`) | a plan that already went through a full wave, re-dispositioned from the review sidecars on disk through the same `integrator()` a live wave calls — no fresh judgment dispatched. § Repair. |

**Check `unmatched_targets` on every targeted run.** A target matching nothing is a typo or
non-candidate; a run that quietly drops one is worse than a refusal.

**When NOT to use:** no roadmap yet → `coordinator:roadmap-planning`. One baton →
`coordinator:sizing`, then `coordinator:plan`. Plans exist and need executing →
`coordinator:execute-plan`. A batch of bugs rather than roadmap batons → `coordinator:bug-blitz`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches named below are constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests the actions that skill performs. A harness line permitting dispatch "unless the user requested it" is therefore **satisfied here, not overridden** — no precedence claim is needed and none is made. Re-asking spends the very context the dispatch exists to protect. The rule attaches to skill entry and dissolves no PM-authored gate: keyword-gated skills gate entry, and every gate a skill names for itself still binds — per-session cross-repo-commit assent, ask-before-external-action, and any other this skill's own body names. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## The two gates — read them, never derive them

One `blocked_by` edge, two questions. **Planning** may start when every blocker is coded *or*
carries a review-approved plan. **Execution** may start only when every blocker is coded. Tripwire:
`A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.

Both come off disk from one op. **Never hand-derive either from `blocked_by`.**

Invoke `coordinator-invoke` per the ladder in `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`
— rung 0 (Shape W, the `.exe` launcher) on a PowerShell host:

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.plan_gate '{"roadmap_id":"<id>"}'`

Per candidate baton it returns both gates with the blockers holding each shut, the linked plan and
status, whether it's sized, its `planning_wave`; plus `waves`, `cycles`, `unresolved_blockers`,
`held`, `counts`.

**It reports, never refuses.** Refusal is yours.

---

## The flow — a loop with no judgment in it

**This runs at Sonnet.** Opus-tier judgment happens INSIDE a wave — `blitz-em` sizes and gates,
reviewers review. The driver is mechanism: read a gate, fire, land, repeat. A call needed to drive
it is a loop defect, not a job for a smarter driver.

### 0. Preflight — confirm the engine is reachable

Before the first call, resolve the launcher per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md` (rung 0 / Shape W on PowerShell;
POSIX rung 2 otherwise). Unresolved — no settings home, no launcher, plugin absent from this
session's list — **stop and report**: no coordinator engine reachable from this session. Never
enter `roadmap.plan_gate`, `roadmap.blitz_land`, or a wave dispatch, and never fabricate a gate or
wave result to compensate.

### 1. Read the gate

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.plan_gate '{}'`

| Field | If non-empty | Response |
|---|---|---|
| `unresolved_blockers` | an edge names no record on disk | Read `baton` first. Stop ONLY for a wave member about to fire; otherwise report and proceed — the gate already fails that baton CLOSED. |
| `cycles` | batons block each other | Stop and report the named members. |
| `counts.unschedulable` | blockers this pass cannot clear | Proceed; excluded by design. |

**A blocker naming a peer EM (`doe-claude-em`, `claude-klabauter-em`) is the standing case, not a typo
to repair.** `blocked_by` takes stub ids and `handoff_id`s, so a role name resolves to no record and
lands here permanently — the shape a baton waiting on a cross-repo answer wears. **Never clear one by
deleting the edge**: the edge is the only thing holding both gates shut, so removing it makes the
baton a live candidate the moment the sweep re-reads. It clears when the peer answers.

**An edge is a DISCOVERED dependency, never a way to suppress a candidate.** A baton you decided
not to fire owes nothing to anybody; an edge the gate cannot resolve fails it CLOSED forever.

**Suppression is a HOLD: three flat baton keys the gate reads —
`plan_blitz_hold_reason`, `plan_blitz_hold_cite`, `plan_blitz_hold_until`.** The gate sets
`candidate: false` and reports the baton under `held`. **A hold with no reason is not honoured.**
`until:` holds a real expiry. `--exclude` narrows one fire and is retyped every run; a hold is the
durable record.

**`external_gate` on a BATON record does nothing, and reads as though it does.** It is real on PLAN
SPINE ROWS, not on a baton. Wiki: § Trimmed rationale.

### 2. Scaffold the trail and freeze the gate

`state/plan-blitz/<run-id>/wave-<N>.gate-report.json`, `<run-id>` being this run's UTC start as
`YYYYMMDDTHHMMSSZ`. The workflow has no filesystem primitive: an unscaffolded directory means every
sidecar write lands nowhere.

| Rule | The tell if you skip it |
|---|---|
| **One report PER WAVE, named for its wave.** Each wave freezes its own, after the previous wave landed. Pass the path to `emit-wave-fire.py`, which refuses a report frozen against an earlier landing declaration. | An earlier report is shape-right and time-wrong: it reads as a healthy wave carrying plans since approved or open in a live agent. |
| **Pass `--bare`** so a successful invoke prints `result` alone; an error still prints the whole envelope. | Without it you freeze a JSON-RPC envelope one level too deep, so a reader finds no `waves`/`batons` and reports an EMPTY WAVE. Tripwire: `AN-ENVELOPE-FROZEN-AS-A-GATE-REPORT-READS-AS-AN-EMPTY-WAVE`. |
| **Freeze by redirection** — `1> gate-report.json 2> gate.stderr`. | `ConvertFrom-Json \| ConvertTo-Json` truncates rows at default depth; `2>&1` folds engine stderr into the JSON. |
| **Read back with `utf-8-sig`.** | PowerShell 5.1 writes a UTF-8 BOM; pwsh 7 does not, and a BOM fails a plain `json.load`. |

### 2a. Check the wave for finished work

One pure read before any agent is dispatched:

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/recycle-check.py" --repo-root <repo> \
        --gate-report <the frozen report> --exclude-run <this run-id>

`RECYCLED` (exit 1): repair by re-running that landing with the SHA; **never drop the baton by
hand**, which leaves it to recycle. `RESURRECTED` (exit 1): remove or re-archive the live copy.
Verdict meanings in full: wiki, § Trimmed rationale. Tripwire:
`A-FINISHED-BATON-THE-LANDING-NEVER-STAMPED-COMES-BACK-AS-A-CANDIDATE`.

### 3. Fire the wave — emit it; never hand-write the args

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/emit-wave-fire.py" \
        --repo-root <abs> --trail-dir <abs> --wave-index N --wave-number N \
        --gate-report <trail-dir>/wave-N.gate-report.json

It reads the frozen report, derives every per-baton field from it, splits the wave into fires at the
cap, binds each fire's args into a standalone `.mjs` through claude-klabauter's `workflow.bind_args`, and
prints one `Workflow({ scriptPath })` line per fire — with no `args` at all, since they are bound
into the file. Fire each printed line. Pass `--plugin-agents-available true` where `coordinator:*`
types resolve. `workflows/plan-blitz.mjs`'s args contract is the source of truth for a field: read
it, never hand-assemble one.

| Rule | The tell |
|---|---|
| **Never hand-type an args object.** | A derived field can be dropped silently; an emitted script is on disk and re-readable/re-firable/diffable. Tripwire: `A-HAND-TYPED-WAVE-ARG-IS-AN-UNARCHIVED-FIRE`. |
| **An emitted fire is a SNAPSHOT, never a handle — RE-EMIT, never re-fire as found.** Diff a script emitted before your last workflow fix against the live `plan-blitz.mjs`, or re-emit. | It binds this host's paths and the workflow body as it stood at emit time; the bug fires on CONTENT, not age. |
| **Never retro-patch a fire that already ran.** | The archive is what ran. |
| **Patching to resume re-runs every agent DOWNSTREAM of the edit, not none.** Decide by phase order, never diff size. | Resume caches on `(prompt, opts)`, and prompts interpolate the workflow's own helpers, so a downstream cache key changes too. |
| **Pass `--wave-number` with the run's own wave count.** Omit on a one-wave run. Never hand-edit to renumber. | `--wave-index` selects which wave to fire (stays 0); `--wave-number` names the bound `waveIndex`, fire filename and trail slot. |
| **At most 8 batons per fire.** A larger wave is drained by several fires at the same `waveIndex`; the emitter splits, do not renumber. | `waveIndex` is what the gate computed, not a fire counter; the sidecar keys off the fire's own baton set. |
| **`--exclude <baton-id>` narrows what is FIRED, never what the gate computed.** | Its one case: a wave already part-fired, where re-emitting a live baton runs two waves against one plan. |
| **Search the trail RECURSIVELY; order slots by INTEGER wave index, never lexically.** `recycle-check.py :: _slot_order` is that ordering. | `wave-10-…` sorts before `wave-2-…` as text; each fire's own slot is that baton's record from a DIFFERENT fire. |

**Fires may run CONCURRENTLY, and the driver owns disjointness — the gate cannot.** A baton being
planned right now still reads as needing planning: nothing on disk changes until that fire lands.

- **Subtract your own in-flight set from every fresh gate read**, or firing them plans one baton
  twice — whichever lands second overwrites the first. Keep the set in the run's own notes.
- **Disjointness is on `planPath`, not just baton id** — several batons share one plan, and two
  fires naming the same plan write one file, silently. Same plan, same fire, or non-overlapping
  fires. **`emit-wave-fire.py._split` enforces that WITHIN an emit** — your duty is ACROSS emits:
  subtract in-flight `planPath`s before the next emit.
- **Subtract adjudicated batons too** — a `pulled` baton stays a candidate by design and returns at
  the head of the next read; re-firing it re-runs the wave that just judged it. Fire it again once
  its pull reason is addressed. Tripwire: `A-GATE-READ-DOES-NOT-KNOW-A-FIRE-IS-RUNNING`.
- **Re-freeze the gate before re-emitting a baton whose plan you edited** — a planner reads the
  BATON, not your settlement, so re-firing re-authors the plan over your ruling silently. The
  emitter warns when a plan changed after the frozen report.
- **A hold that only you remember is not a hold.** Write a standing reason in the trail's
  `RUN-NOTES.md`, and the baton record when it belongs there — a gate read sees that.

**`dispositionsCli` and `provisionSidecarCli` are resolved caller-side, by `emit-wave-fire.py`**
— launcher first, then `--engine-root`'s own `coordinator/bin/`. Pass `--dispositions-cli` /
`--provision-sidecar-cli` only to OVERRIDE that; omitting on a box with no install lets a reviewer
invent its own sidecar path, losing the disposition record silently. **A resolved
`provision-sidecar` whose findings path carries no `subagent-share` segment is a REFUSAL too.**
Tripwire: `A-SIDECAR-THE-DISPOSITION-OP-REFUSES-LOSES-ONLY-THE-RECORD`.

**A box with no install is Rung N, not a broken resolution** — every launcher rung fails
command-not-found and reads as "this CLI does not exist", while the engine source is on disk
regardless, so pass `--engine-root`. Where the only checkout carrying `workflow.bind_args` is
Claude-klabauter's unstamped authoring tree, add `--live-engine-tree`: it takes the engine's live-tree path for
the BIND CALL alone and refuses a root that carries a build stamp. Tripwire:
`A-PUBLISHED-MIRROR-OLDER-THAN-AN-OP-REFUSES-AS-A-MISSING-ENGINE`.

**Every baton carries `executionOpen`, read off `execution_gate.open`.** No default: an XS
dispatches only when its gate is open; a baton missing the field dispatches nothing and returns as
a candidate every later wave. `emit-wave-fire.py` derives it and refuses rather than defaults.

**Resolve `${CLAUDE_PLUGIN_ROOT}`; never pass a repo-relative path.** The plugin root differs by
tree — under the DoE source repo it is the `coordinator/` subdirectory, in an installed or mirrored
plugin it IS the root. A path written `coordinator/workflows/...` resolves only where the cwd happens
to be DoE and elsewhere fails as a MISSING FILE, which reads as "the vehicle does not exist" rather
than "the path was not resolved" — the more expensive of the two wrong conclusions.

Then wait. **Do not read the trail to decide anything** — the wave needs no input between fire and
return; intervening mid-wave overrides a judgment `blitz-em` was dispatched to make.

### 4. Commit the wave's XS work, then land it — one call over every fire of the wave

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/land-wave.py" \
        --repo-root <abs> [--shipped-in <sha>] <fire-result.json> ...

One file per fire — the harness's task-output file, or the bare result pulled out of it; both are
read. It lands each fire through `roadmap.blitz_land`, **sums the three lanes across every fire**,
and states the stop condition from that sum. It refuses before landing anything if the fires
disagree about `waveIndex`, or if any fire dispatched XS and no `--shipped-in` was given. It
orders the calls and does the arithmetic; it decides, fires and re-queues nothing.

It writes the wave's own `wave-<n>.landing.json` into the trail, which the NEXT session reads
instead of your stdout. **Never redirect its stdout onto that path** — text report and script write
interleave into an unparseable file.

**Commit before landing whenever the wave dispatched any XS.** `close_dispatched` stamps the baton
`shipped` with a `shipped_in` SHA and this op does not commit, so a stamp written first would cite
a commit that doesn't exist. Pass that SHA as `shipped_in`; without it the XS lane refuses.

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.blitz_land '{"wave_result": <the workflow's return value verbatim>, "shipped_in": "<sha of the commit carrying the XS work>"}'`

`roadmap.blitz_land` executes the readiness gate's verdicts: links each `ready` plan then stamps
`approved`, mints a baton per `replan` carrying the brief verbatim, leaves `pulled` as the EM left
it, and returns `next_wave` off a **fresh** gate read taken after the writes.

**Three lanes land differently, and the op picks by route — you do not.**

| Route | Size | What landing does |
|---|---|---|
| `plan` | M / L | link the plan to its baton, then stamp `approved` — opens the next wave's planning gates |
| `spec-dispatch` | S | park the spec onto the baton, stamp execution-ready (four-field `execution_authorized_*` + `handoff_phase: execution`), so `/execute-plan` resolves it as a straight dispatch |
| `dispatch` | XS | work already done in the wave's Dispatch phase; landing stamps `shipped` with `shipped_in`, making it terminal |

**Why S parks rather than approves.** An S is a straight dispatch, not decision-weight work; its
plan stays `draft` by design: `needs_plan` keys off the execution stamp for these, so a later
sweep does not re-plan marching orders. Wiki: § Trimmed rationale.

**Never hand-stamp `status: approved` instead** — the op links before stamping and refuses what it
can't link; a hand stamp skips that check.

**Read `refused[]` on every landing** — each entry names a baton and why, never a thing to route
around.

### 5. Loop

Fire `next_wave` and land it. Repeat.

**Stop conditions, all mechanical:**

- `next_wave.batons` is empty.
- `--waves` exhausted.
- A wave lands zero `approved` **and** zero `execution_ready` **and** zero `closed` — it opened
  nothing, so the next wave is this wave again. Report and stop rather than spinning.
  **Zero `approved` alone is not the test.** An all-S ready set approves nothing by construction
  and still advances: `blitz_land` parks each S execution-ready, and `needs_plan` keys off that
  stamp (§ Three lanes above). Tripwire: `AN-ALL-S-WAVE-APPROVES-NOTHING-AND-STILL-ADVANCES`.
  **It is a WAVE-level test, not a fire-level one** — a wave over 8 is drained by several fires
  sharing one `waveIndex`, but `blitz_land` takes ONE fire's result. Measured 2026-09-10 on
  project-rag, one fire of a five-fire wave: `approved: 0`, `execution_ready: 2`, and a candidate
  set that still falls — `needs_plan` 27 to 24. Sum the three lanes across every fire at this
  `waveIndex` first.
  **And it only applies to a wave that FINISHED** — a part-way-killed fire shows the same
  zero-lane signature, so check completion BEFORE reading the lanes (wiki, § Trimmed rationale, has
  the diagnostic tells). **Never land an unfinished fire**; resume instead — a run replays only the
  agents that died, and resumes only in its own session; after that re-emit and re-fire, closing a
  finished XS with `archive-stamp-cli ship-handoff <path> --sha <sha>`. Tripwire:
  `AN-UNFINISHED-WAVE-IS-NOT-A-WAVE-THAT-OPENED-NOTHING`.
- `refused[]` is non-empty — report and stop; a landing that could not complete must not be built
  on.
- `surfacedToPm` is non-empty — those need a PM answer. Carry them out; **never re-queue one.**

**What the driver escalates rather than decides:** an unresolved blocker, a cycle, any `refused`
entry, anything in `surfacedToPm`, and a wave that lands nothing. Every other outcome has a defined
next call.

---

## Rules that hold across every wave

**Review fires unconditionally; the EM gates once, at the end.** Gating review on the EM makes
addressing a finding cost effort and ignoring it cost nothing. Tripwire:
`A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ`.

**Host availability on the box the wave runs on is never a pull reason** — the gate asks whether
the plan can be RUN, by whoever runs it on the host it names, not whether it can run here, now.
A plan whose rows are withheld behind a declared `external_gate` is READY, and the withheld rows
are a schedule fact. Pull for properties of the PLAN: an unapplied finding, an unsettled
escalation, self-contradictory acceptance criteria. Tripwires:
`A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`, `THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON`.

**One reviewer-attributed option is a recommendation, not a choice and not a dead end.** Contested
options are arbitrated by the resolve pass, which picks one; exactly one is applied or declined
with a reason. Tripwire: `A-SINGLE-REVIEWER-OPTION-IS-A-RECOMMENDATION-NOT-A-DEAD-END`.

**No reviewer is prescribed in a plan file** — the blitz-em resolves reviewers per baton.

**`BLOCKED` and `PIVOT` are different questions, not a severity ladder.** `BLOCKED` means "wrong
until you fix these" — the integrator applies the findings and the fixed plan is approved the same
wave. `PIVOT` means "this direction cannot proceed" — no findings repair it. Test: name what a
competent author changes to make it right and it's `BLOCKED`, however large; `PIVOT` requires a
stated premise failure. Tripwire: `A-BLOCKED-REVIEW-IS-NOT-A-PIVOT`.

**`PIVOT` routes; it does not halt** — it becomes a replan baton, and the other N-1 plans finish.

**Every reviewer's verdict survives, separately.** A PIVOT does not delete co-reviewer findings —
they're triaged `Suspended (PIVOT)` and carried into the replan brief.

**Never blitz a claimed or `in_flight` baton** — a live holder has it. The op excludes them; do not
add them back by hand.

**Never open a gate the engine says is shut** — fix the blocking edge or clear the blocker.

**Never let the blitz-em resolve a PM decision.** `route: pm-decision` and XL exits leave it in
`surfacedToPm` — the blitz-em is an EM proxy, never a PM proxy.

**`approved` is not `mise-prepped`, and a wave never stamps one.** Landing opens the *planning*
gate; the `mise_prepped_by/_at/_sha/_findings` attest says a hands-off run may fire the plan without
an overseer, stamped by `plan.stamp_prepped` outside this skill, driven by `/mise-prep`. This skill
stops at *ready to execute* in both vocabularies.

**A wave's body edits invalidate a stamp; its frontmatter writes do not.** `mise_prepped_sha` is
`canonical_body_sha` of the plan BODY, frontmatter excluded, so `blitz_land`'s writes leave an
existing stamp intact; a review-integrator body rewrite makes the plan STALE, which re-gates rather
than re-stamps. Never read `mise_prepped_by` for presence. Tripwire:
`A-PRESENT-MISE-PREPPED-STAMP-IS-NOT-A-CERTIFICATION`; consumer contract:
`coordinator/docs/wiki/mise-prepped-attest.md`.

---

## Repair

**Emit it; never hand-build `repairBatons`** — same reasons as § Fire the wave: an args object in a
tool call isn't on disk, so the repair can't be re-read, re-fired or diffed.

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/emit-wave-fire.py" \
        --repo-root <abs> --trail-dir <abs of the run whose records you are repairing> \
        --repair <baton-id> [--repair <baton-id> ...]

It resolves each baton's pointer records under the rules below, refuses per baton with the reason
on stderr, and writes `repair-fire-<n>.mjs` into the trail, numbered past any repair already there.
Fire the printed `Workflow({ scriptPath })`, with no args. No gate report is read.

The bound shape, for reading not writing a fire — one entry per plan re-dispositioned:

```
{ batonId, planPath, reviews: [ <pointer record>, ... ], unresolvedPointers: [ ... ] }
```

**Where the records come from.** Each pointer record: `{ sidecarPath, verdict, premiseFailure }`,
from the latest WAVE slot only (`recycle-check.py :: _slot_order`). A record whose `sidecarPath`
still exists is a review; a gone target is an `unresolvedPointer`. Mechanics in full: wiki, §
Trimmed rationale.

**Refusals, all loud, none silent.** The whole baton or none of it when: no `planPath`; any
`unresolvedPointers`; empty `reviews`; a record missing `verdict`; or no `trailDir`. A missing
`verdict` is the pre-contract bare-path shape — a trail that old is unrepairable.

**Check the plan has not moved under review** — a pointer names its plan by path, never version.
Tripwire: `A-REVIEW-SIDECAR-NAMES-ITS-PLAN-BY-PATH-NOT-BY-VERSION`.

**A repair produces an integration, never a verdict — a repaired plan is not yet `approved`.** No
landing exists for a repair result: `blitz_land` lands a WAVE. Approve via one targeted re-fire,
safe because the emitter binds the plan the trail already holds even unlinked. Re-freeze the gate
first if you edited the plan. Do not hand-stamp `approved`.

**What it does not do.** It dispatches no `sizingScout`, no `planner`, no `reviewerAgent`. The one role reached is
`integrator()`, unforked, holding no `Agent`/`Task` tool. A premise failure PIVOTs as in a wave.

---

## Anti-scope

- Does not author roadmap batons (`coordinator:roadmap-planning`).
- Does not execute plans, and never opens an execution gate. It stops at *ready to execute*. The
  landing is durable on disk (`status: approved`, `governing_plan`), so mise-prep's entry reads it
  back through `roadmap.plan_gate` rather than opening a gate itself. Consumer:
  `skills/plan-blitz/mise-prep-entry.py`. Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.
- Does not ratify sizings on the PM's behalf.
- Does not review code — the reviewers in a wave review **plans**.

---

## Test Surface

No runtime test for this skill body — prose doctrine, not code. The executable surface is
in claude-klabauter (`coordinator_core/roadmap/tests/test_plan_gate.py`,
`coordinator_core/ops/tests/test_roadmap_plan_gate.py`) and this repo's
`coordinator/tests/test_plan_blitz_contract.py`. Per-token thresholds: fleet doctrine wiki, §
Greppability thresholds.
