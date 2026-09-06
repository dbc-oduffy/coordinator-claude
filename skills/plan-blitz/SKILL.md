---
name: plan-blitz
description: "PM-GATED. Sweep every baton in the repo that lacks an approved plan, in waves — sonnet scouts size, an Opus EM finalises, Opus planners write, plans are reviewed and integrated without the EM in the loop, and the EM gates readiness at the end. Or target named batons. Wave N+1 fires on wave N's approvals, not its landings."
description-budget: 320
version: 1.0.0
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent", "Skill", "Workflow", "AskUserQuestion", "TaskCreate", "TaskUpdate", "TaskGet", "TaskList"]
argument-hint: "[<baton-id> ...] [--roadmap-id <id>] [--waves <n>] [--dry-run]"
---

# Plan-blitz — a roadmap's worth of plans, in waves

Consumes a roadmap that already exists and produces plans for it, N batons per wave instead of one
baton per session. Argument and worked rationale live in the fleet doctrine wiki under this
skill's own name — read it when a rule here looks wrong, never to decide whether to follow one.
The two tripwires below are the greppable entry points.

---

## Two modes

**Sweep (default, no arguments).** Every baton in the repo that lacks an approved plan. That set is
`needs_plan` in the engine's reply — no linked plan, or one that has not cleared review — and it is
the target set precisely because an approved plan is the thing that opens the next wave. A baton
whose plan is already approved is not in it: it needs no planning work, and stays in the graph only
as a satisfied blocker for its dependents. `--roadmap-id` narrows the sweep to one roadmap.

**Targeted (`<baton-id> ...`).** The EM's adjudged prioritisation, or the PM's targeting. Pass ids
(`stub_id`, `handoff_id`, or filename stem) as `targets`. Everything unnamed stops being a
candidate but stays a fully-resolved BLOCKER — narrowing what you are asking about never narrows
what the answer is computed from.

**Check `unmatched_targets` on every targeted run.** A target that matched nothing is a typo or a
baton that is not a candidate (claimed, `in_flight`, already approved). The engine names it rather
than silently planning N-1 batons; a targeted run that quietly drops one is worse than a refusal,
because the drop looks like completion.

**When NOT to use:** no roadmap yet → `coordinator:roadmap-planning` (this consumes stubs, it never
authors them). One baton → `coordinator:sizing`, then `coordinator:plan`. Plans exist and need
executing → `coordinator:execute-plan`. A batch of bugs rather than roadmap batons →
`coordinator:bug-blitz`.

**Dispatch authorization — invoking this skill IS the request.** The dispatches below are
constitutive steps of this skill, not a separate thing to get cleared: invoking a skill requests
the actions that skill performs. Re-asking spends the very context the dispatch exists to protect.
The rule attaches to skill entry and dissolves no PM-authored gate — every gate this body names
still binds. Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

---

## The two gates — read them, never derive them

One `blocked_by` edge, two questions. **Planning** may start when every blocker is coded *or*
carries a review-approved plan. **Execution** may start only when every blocker is coded.
Full statement and the `approved`-not-`reviewed` seam: tripwire
`A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`.

Both come off disk from one engine op. Never hand-derive either from `blocked_by` — an EM deriving
it by eye derives it differently each time, and the difference stays invisible until a wave fires
against a gate that was never open.

Invoke `coordinator-invoke` per the ladder in `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`
— rung 0 (Shape W, the `.exe` launcher through the call operator) on a PowerShell host:

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.plan_gate '{"roadmap_id":"<id>"}'`

It returns, per candidate baton: both gates with the blockers holding each shut, the linked plan
and its status, whether the baton is sized, and its `planning_wave`. Plus `waves` (the wave
membership lists), `cycles`, `unresolved_blockers`, and `counts`.

**It reports; it never refuses.** Refusal is yours. That is deliberate: a derived read that has
gone stale should mis-report, not silently block live work.

---

## The flow — a loop with no judgment in it

**This runs at Sonnet.** Every Opus-tier judgment in this pipeline happens INSIDE a wave —
the `blitz-em` sizes and gates, the reviewers review. The driver outside the wave is mechanism:
read a gate, fire, land, repeat. If driving it ever requires a call, that is a defect in the loop,
not a job for a smarter driver — the escalation rules below say what to do instead of deciding.

**1. Read the gate.**

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.plan_gate '{}'`

Three fields before anything else, each with a mechanical response:

| Field | If non-empty | Response |
|---|---|---|
| `unresolved_blockers` | an edge names no record on disk | **Stop and report.** An authoring defect; fixing it is not the driver's call. |
| `cycles` | batons block each other | **Stop and report** the named members. |
| `counts.unschedulable` | blockers this pass cannot clear | Proceed; they are excluded by design. |

**2. Scaffold the trail and freeze the gate.** `state/plan-blitz/<run-id>/gate-report.json`.
The workflow has no filesystem primitive — an unscaffolded directory means every sidecar write
lands nowhere and the readiness gate reads an empty trail.

**3. Fire the wave.** Batons come from `waves[0]`, **at most 8 per fire** (§ batching above).

    Workflow({ scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/plan-blitz.mjs",
               args: { waveIndex: N, trailDir: "<abs>", gateReportPath: "<abs>",
                       pluginAgentsAvailable: <true|false>, batons: [...] } })

Resolve `${CLAUDE_PLUGIN_ROOT}` — do not pass a repo-relative path. The plugin root differs by
tree: under the DoE source repo it is the `coordinator/` subdirectory, and in an installed or
mirrored plugin it IS the root. A path written `coordinator/workflows/...` resolves only when the
cwd happens to be DoE, and elsewhere fails as a MISSING FILE, which reads as "the vehicle does not
exist" rather than "the path was not resolved" — the more expensive of the two wrong conclusions.

Then wait. **Do not read the trail to decide anything** — reading it to follow along is fine and
costs nothing, but the wave needs no input between fire and return. A driver that intervenes
mid-wave is overriding a judgment the `blitz-em` was dispatched to make.

**4. Land it — one op, not a checklist.**

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.blitz_land '{"wave_result": <the workflow's return value verbatim>}'`

`roadmap.blitz_land` executes the verdicts the readiness gate already made: it links each `ready`
plan to its baton and *then* stamps it `approved`, mints a baton per `replan` carrying the brief
verbatim, leaves `pulled` where the EM left it, and returns `next_wave` computed from a **fresh**
gate read taken after the writes.

**Three lanes land differently, and the op picks by route — you do not.**

| Route | Size | What landing does |
|---|---|---|
| `plan` | M / L | link the plan to its baton, then stamp it `approved` — this is what opens the next wave's planning gates |
| `spec-dispatch` | S | park the spec onto the baton and stamp it execution-ready (four-field `execution_authorized_*` + `handoff_phase: execution`), so `/execute-plan` resolves it as a straight dispatch — mise-en-place tier |
| `dispatch` | XS | already done, inside the wave's Dispatch phase |

**Why S parks rather than approves.** An S is a straight dispatch, not decision-weight work.
Sending one round a full review cycle and then handing back an un-actioned baton is what made the
EM's own sizing fight the rest of this skill: if calling something S condemned it to the queue, the
honest S got inflated to M. Sizing that bends toward its downstream route is corrupted sizing.
An S baton's plan stays at `draft` by design — `needs_plan` keys off the execution stamp for these,
so a later sweep does not re-plan work that already has its marching orders.

**Never hand-stamp `status: approved` instead.** The op links before it stamps and refuses to stamp
what it cannot link, because an approval that resolves to no baton is a silent no-op that reads as
success — measured twice on this repo, once on a plan the pipeline authored and once on a 457-line
plan authored months earlier. A hand stamp skips the check that exists for that.

**Read `refused[]` on every landing.** Each entry names a baton and why. A refusal is the op
declining to write something misleading; it is never a thing to route around.

**5. Loop.** Fire `next_wave` and land it. Repeat.

**Stop conditions, all mechanical:**

- `next_wave.batons` is empty — nothing left to plan.
- `--waves` exhausted.
- A wave lands zero `approved` — it opened nothing, so the next wave is this wave again. Report
  and stop rather than spinning.
- `refused[]` is non-empty — report and stop; a landing that could not complete must not be
  built on.
- `surfacedToPm` is non-empty — those need a PM answer. Carry them out; **never re-queue one.**

**What the driver escalates rather than decides:** an unresolved blocker, a cycle, any `refused`
entry, anything in `surfacedToPm`, and a wave that lands nothing. That is the complete list. Every
other outcome has a defined next call.

---

## Rules that hold across every wave

**Review fires unconditionally; the EM gates once, at the end.** No mid-wave permission to review,
no per-plan "does this need the Staff Engineer?" Gating review on the EM makes addressing a finding cost effort
and ignoring it cost nothing; firing it by default inverts that, so declining a finding becomes the
deliberate act. The EM's authority is not reduced — it moves to reading a durable trail. Tripwire:
`A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ`.

**No reviewer is prescribed in a plan file.** Reviewers are resolved per baton by the blitz-em from
what that plan actually needs. A reviewer named on every plan is a reviewer nobody chose.

**`BLOCKED` and `PIVOT` are different questions, not a severity ladder.** `BLOCKED` means "wrong
until you fix these" — the direction holds, the integrator applies the findings, and the fixed plan
can be approved in the same wave. `PIVOT` means "this direction cannot proceed" — no set of findings
repairs it. The test that separates them: if you can name what a competent author changes in this
plan to make it right, it is `BLOCKED`, however large that change is. Reviewers picking by "how bad
is it" pick wrong, which is why `PIVOT` is reached by judging direction and must carry a stated
premise failure. Tripwire: `A-BLOCKED-REVIEW-IS-NOT-A-PIVOT`.

**`PIVOT` routes; it does not halt.** A reviewer rejecting a plan's premise has produced exactly
the evidence a replan needs. The wave records it, turns it into a replan baton, and the other
N-1 plans finish. Killing the wave to report one pivot discards the work that succeeded.

**Every reviewer's verdict survives, separately.** Sidecar paths are assigned per reviewer, a mixed
set is named in the trail, and a pivot's suspension of the plan does not delete the co-reviewers'
findings — they are triaged as `Suspended (PIVOT)` and carried into the replan brief. Two reviewers
choosing the same obvious filename cost a whole BLOCKED review once; assignment is why they cannot
again.

**Never blitz a claimed or `in_flight` baton.** They have a live holder, and a wave writing a plan
for work somebody is already doing races them. The op excludes them from the candidate set; do not
add them back by hand.

**Never open a gate the engine says is shut.** If `roadmap.plan_gate` reports a planning gate shut,
it is shut. The repair is to fix the blocking edge or clear the blocker.

**Never let the blitz-em resolve a PM decision.** `route: pm-decision` and XL exits leave the wave
in `surfacedToPm`. The blitz-em is an EM proxy, never a PM proxy.

---

## Anti-scope

- Does not author roadmap batons (`coordinator:roadmap-planning`).
- Does not execute plans, and never opens an execution gate. It stops at *ready to execute*.
- Does not ratify sizings on the PM's behalf.
- Does not review code. The reviewers in a wave review **plans**.

---

## Test Surface

No runtime test for this skill body — prose doctrine, not executable code. The executable surface
is in claude-klabauter (`coordinator_core/roadmap/tests/test_plan_gate.py`,
`coordinator_core/ops/tests/test_roadmap_plan_gate.py`) and in this repo's
`coordinator/tests/test_plan_blitz_contract.py`, which asserts the workflow script conforms to the
Workflow correctness contract and that the doctrine below stays greppable.

| # | token | file | expect | threshold reason |
|---|---|---|---|---|
| 1 | `A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE` | this file + `skills/pickup/SKILL.md` + `skills/execute-plan/SKILL.md` | ≥3 | the two-gate rule is inert if only the skill that introduced it knows about it |
| 2 | `roadmap.plan_gate` | this file + both consuming skills | ≥3 | a gate nobody reads is a gate nobody honours |
| 3 | `A-BLITZ-WAVE-THAT-GATES-ON-THE-EM-IS-NOT-A-BLITZ` | this file + `agents/blitz-em.md` | ≥2 | 1 means only the self-reference survives |
| 4 | `plan-blitz.mjs` | this file | ≥1 | the vehicle is named, not left to be rediscovered |
