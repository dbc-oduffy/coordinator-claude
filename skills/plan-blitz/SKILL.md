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
baton per session. Argument and worked rationale live in the fleet doctrine wiki under this
skill's own name — read it when a rule here looks wrong, never to decide whether to follow one.
The two tripwires below are the greppable entry points.

---

## Three modes

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

**Repair (`--repair <baton-id> ...`).** Re-dispositions a plan that already went through a full
wave — its reviews are already on disk — without dispatching a fresh judgment, by reading the
plan's own review sidecars back through their structured pointer records and calling the same
`integrator()` a live wave calls. See § Repair below for what makes a baton unrepairable and the
caller-side `repairBatons` construction procedure.

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
| `unresolved_blockers` | an edge names no record on disk | **Read the `baton` column first** — see below. Stop only for a member of the wave you are about to fire. |
| `cycles` | batons block each other | **Stop and report** the named members. |
| `counts.unschedulable` | blockers this pass cannot clear | Proceed; they are excluded by design. |

**An unresolved blocker is scoped to its own baton, not to the run.** The gate fails it CLOSED —
both gates shut, the baton out of every wave — so a sweep over the other batons is planning
against no unread gate. Stop only when a named `baton` is a member of the wave you are about to
fire; otherwise report the entries and proceed. Halting a 40-baton sweep over a defect on a baton
the engine already excluded is the more expensive error, and it recurs on every later invocation.

**A blocker naming a peer EM (`doe-claude-em`, `claude-klabauter-em`) is the standing case, and it
is not a typo to repair.** `blocked_by` takes stub ids and `handoff_id`s, so a role name resolves
to no record and lands here permanently — the shape a baton waiting on a cross-repo answer wears.
**Never clear one by deleting the edge**: the edge is the only thing holding both gates shut, and
removing it makes the baton a live planning candidate the moment the sweep re-reads. It clears
when the peer answers.

**2. Scaffold the trail and freeze the gate.** `state/plan-blitz/<run-id>/gate-report.json`.
The workflow has no filesystem primitive — an unscaffolded directory means every sidecar write
lands nowhere and the readiness gate reads an empty trail.

**Redirect `coordinator-invoke`'s stdout and what you froze is a JSON-RPC envelope** — the gate's
own `waves`, `batons` and `counts` sit one level down, under `result`. That is the shape the
readers below accept, and the shape to build the baton array from. A machine reader that asks the
envelope for `waves` finds none and reports an EMPTY WAVE, which is the same sentence a genuinely
empty wave produces — so the wave fires with step 2a skipped and nothing says so. Tripwire:
`AN-ENVELOPE-FROZEN-AS-A-GATE-REPORT-READS-AS-AN-EMPTY-WAVE`. Redirect stderr separately: the
engine writes a `[warm-settings]` line there, and `2>&1` folds it into the JSON.

**The readers tolerate either shape anyway** — `recycle-check.py` and `emit-wave-fire.py` both unwrap an envelope — but freeze the documented shape rather than relying on that: a consumer written later will not.

**2a. Check the wave for finished work.** One pure read, before any agent is dispatched:

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/recycle-check.py" --repo-root <repo> \
        --gate-report <the frozen report> --exclude-run <this run-id>

`RECYCLED` (exit 1) names a baton whose execution record from an earlier wave says the work
FINISHED, and which the gate still returns as a candidate — its landing never stamped it, because
`blitz_land` refuses the XS lane without `shipped_in`. The repair is that landing, re-run with the
SHA; **never drop the baton from this wave by hand**, which leaves it to recycle into the next one.
`back` entries are `completed: false` or `blocked-on-preflight` and are correctly here. Tripwire:
`A-FINISHED-BATON-THE-LANDING-NEVER-STAMPED-COMES-BACK-AS-A-CANDIDATE`.

**3. Fire the wave. Emit it; never hand-write the args.**

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/emit-wave-fire.py" \
        --repo-root <abs> --trail-dir <abs> --wave-index N

It reads the frozen gate report, derives every per-baton field from it, splits the wave into
fires at the cap, binds each fire's args into a standalone `.mjs` through claude-klabauter's
`workflow.bind_args`, and prints one `Workflow({ scriptPath })` line per fire — **with no `args`
at all**, because they are bound into the file. Fire each printed line. The bound args are this
host's absolute paths, so a fire emitted on another box is re-emitted here, never fired as found.
Pass `--plugin-agents-available true` where `coordinator:*` agent types resolve; the default
fires every role as a generic agent carrying only its inline contract.

**A hand-typed args object is the defect this replaces, not a shortcut past it.** Everything the
args contract can lose, it loses silently: `executionOpen` reached a live wave missing because a
caller copied an example that omitted it, and the wave then dispatched no XS, closed none at the
landing, and reported them under `routedElsewhere`. A derived field cannot be omitted. An emitted
script is also on disk, so it archives with the trail and the fire can be re-read, re-fired and
diffed — an args object inside a tool call is none of those. Tripwire:
`A-HAND-TYPED-WAVE-ARG-IS-AN-UNARCHIVED-FIRE`.

**Pass `--wave-number` with the run's own wave count.** `roadmap.plan_gate` numbers `waves` from
the READ, so every wave arrives as `waves[0]`: `--wave-index` selects which wave of the frozen
report to fire and stays 0, while `--wave-number` names the bound `waveIndex`, the fire filename
and the trail slot. Omit it on a one-wave run. Never hand-edit the frozen report to renumber.

Batons come from `waves[N]`, **at most 8 per fire** (§ batching above). A wave larger than 8 is
drained by several fires at the same `waveIndex`, sharing one trail directory. That is supported:
the wave-scoped sidecar is keyed by the fire's own baton set, so fires do not overwrite each
other's size review. The emitter does that split; do not renumber the wave to separate them —
`waveIndex` is what the gate computed, not a fire counter. **`--exclude <baton-id>` narrows what
is FIRED and never what the gate computed** — its case is a wave already part-fired, where
re-emitting a live baton would run two waves against one plan.

**Every fire writes its records into its OWN leaf of that trail**,
`<trailDir>/wave-<index>-<fireId>/`, returned as `trailSlotDir`. So neither a second fire of one
wave nor a LATER wave re-planning a baton this one already planned overwrites what is on disk —
search the trail RECURSIVELY, and read a second slot holding the same baton as that baton's record
from a DIFFERENT fire rather than a duplicate to reconcile. **Order slots by INTEGER wave index,
never lexically** — `wave-10-…` sorts before `wave-2-…` as text, so a ten-wave run's oldest record
reads as its newest; `recycle-check.py :: _slot_order` is that ordering, do not re-derive it.

The args contract itself lives at the top of `workflows/plan-blitz.mjs` and stays the source of
truth for what the emitter produces. Read it to understand a field; do not assemble it by hand
to fire one.

**Fires may run CONCURRENTLY, and the driver owns disjointness — the gate cannot.** Concurrency is
what makes a 200-baton wave finish, since a fire costs ~50 minutes of wall clock whatever its size.
But `roadmap.plan_gate` reports the batons that need planning, and a baton being planned *right
now* still needs planning: nothing on disk changes until that fire lands. So a driver that re-reads
the gate to build its next fire gets its own in-flight batons back at the head of the list, and
firing them plans the same baton twice — two waves writing one plan file, two size reviews, and
whichever lands second overwrites the first. **Subtract your own in-flight set from every fresh
gate read.** Keep it in the run's own notes; the engine has no session-scoped view to keep it for
you, and adding one would make a derived read authoritative over disk.

**Disjointness is on `planPath`, not just on baton id — this is the one that bites.** Several
batons routinely share one plan: a roadmap plan links every baton it emitted, and on this repo
NINE batons link `docs/plans/2026-07-23-computed-skills-frontage-roadmap.md`. Two fires holding
different batons that name the same plan are two waves authoring one file, and the sidecar keying
above does not help — it makes each fire's SIZE REVIEW safe, and says nothing about the plan.
Whichever integrator writes last wins, silently. Group batons by `planPath` when you build a fire:
same plan, same fire, or different fires that do not overlap in time.

**Subtract adjudicated batons too, for the same fire.** A `pulled` baton stays a candidate by
design — the EM left it where it was — so it also returns at the head of the next read. Re-firing
one immediately re-runs the wave that just judged it, against an escalation nobody has answered in
between. Fire it again when its pull reason is addressed, not because the gate still lists it.
Tripwire: `A-GATE-READ-DOES-NOT-KNOW-A-FIRE-IS-RUNNING`.

**`dispositionsCli` and `provisionSidecarCli` are resolved caller-side, and `emit-wave-fire.py`
does it** — launcher first, then the `--engine-root` checkout's own `coordinator/bin/`, with the
interpreter and any env the registry manifest needs made part of the injected literal. Pass
`--dispositions-cli` / `--provision-sidecar-cli` only to OVERRIDE that, never as the ordinary path.
Omit them on a box with no install and a reviewer invents its own sidecar path: the review runs,
the disposition record is lost, and nothing reports it. **A resolved `provision-sidecar` whose
findings path carries no `subagent-share` segment is a REFUSAL too** — the disposition op rejects
every target without it, so the wave reviews and records nothing. Tripwire:
`A-SIDECAR-THE-DISPOSITION-OP-REFUSES-LOSES-ONLY-THE-RECORD`.

**A box with no install is Rung N, not a broken resolution.** Every launcher rung fails
command-not-found and reads as "this CLI does not exist"; the engine source is on disk regardless,
so pass `--engine-root`. Where the only checkout carrying `workflow.bind_args` is claude-klabauter's
unstamped authoring tree, add `--live-engine-tree` — it takes the engine's live-tree path for the
BIND CALL alone, and refuses a root that carries a build stamp. Tripwire:
`A-PUBLISHED-MIRROR-OLDER-THAN-AN-OP-REFUSES-AS-A-MISSING-ENGINE`.

**Every baton carries `executionOpen`, read off that baton's own `execution_gate.open` in the
gate report.** It is not optional and it has no default: an XS is dispatchable only when its
EXECUTION gate is open, so a baton missing the field fails that test, dispatches nothing, and is
never closed at the landing — it comes back as a candidate in every later wave. The wave reports
it under `routedElsewhere` either way, which is why the omission is silent. The full per-baton
shape is the args contract at the top of `workflows/plan-blitz.mjs`; build the array from the
frozen gate report, never by hand — `emit-wave-fire.py` derives it, and refuses rather than
defaults a baton row carrying no `execution_gate.open`, because a field whose wrong value costs a
whole wave silently cannot have a default.

Resolve `${CLAUDE_PLUGIN_ROOT}` — do not pass a repo-relative path. The plugin root differs by
tree: under the DoE source repo it is the `coordinator/` subdirectory, and in an installed or
mirrored plugin it IS the root. A path written `coordinator/workflows/...` resolves only when the
cwd happens to be DoE, and elsewhere fails as a MISSING FILE, which reads as "the vehicle does not
exist" rather than "the path was not resolved" — the more expensive of the two wrong conclusions.

Then wait. **Do not read the trail to decide anything** — reading it to follow along is fine and
costs nothing, but the wave needs no input between fire and return. A driver that intervenes
mid-wave is overriding a judgment the `blitz-em` was dispatched to make.

**4. Commit the wave's XS work, then land it — one call over every fire of the wave.**

    python3 "${CLAUDE_PLUGIN_ROOT}/skills/plan-blitz/land-wave.py" \
        --repo-root <abs> [--shipped-in <sha>] <fire-result.json> ...

One file per fire — the harness's task-output file the workflow's completion named, or
the bare result pulled out of it; both are read. It lands each fire through
`roadmap.blitz_land`, **sums the three lanes across every fire**, and states the stop
condition from that sum. It refuses before landing anything if the fires disagree about
`waveIndex`, or if any fire dispatched XS and no `--shipped-in` was given.

Read § the op below for what the landing DOES — the helper orders the calls and does the
arithmetic; it decides nothing, fires nothing, and re-queues nothing.

**Commit before landing whenever the wave dispatched any XS.** `close_dispatched` stamps the
baton `shipped` with a `shipped_in` SHA, and this op does not commit — a stamp written first
would cite a commit that does not exist. Pass that SHA as `shipped_in`; without it the XS lane
refuses and those batons stay open, which is the recycling defect, not a cosmetic gap.

    `& "$env:COORDINATOR_SETTINGS_HOME\bin\coordinator-invoke.exe" roadmap.blitz_land '{"wave_result": <the workflow's return value verbatim>, "shipped_in": "<sha of the commit carrying the XS work>"}'`

`roadmap.blitz_land` executes the verdicts the readiness gate already made: it links each `ready`
plan to its baton and *then* stamps it `approved`, mints a baton per `replan` carrying the brief
verbatim, leaves `pulled` where the EM left it, and returns `next_wave` computed from a **fresh**
gate read taken after the writes.

**Three lanes land differently, and the op picks by route — you do not.**

| Route | Size | What landing does |
|---|---|---|
| `plan` | M / L | link the plan to its baton, then stamp it `approved` — this is what opens the next wave's planning gates |
| `spec-dispatch` | S | park the spec onto the baton and stamp it execution-ready (four-field `execution_authorized_*` + `handoff_phase: execution`), so `/execute-plan` resolves it as a straight dispatch — mise-en-place tier |
| `dispatch` | XS | work already done inside the wave's Dispatch phase; landing stamps the baton `shipped` with `shipped_in`, which is what makes it terminal and stops it returning as a candidate |

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
- A wave lands zero `approved` **and** zero `execution_ready` **and** zero `closed` — it opened
  nothing, so the next wave is this wave again. Report and stop rather than spinning.
  **Zero `approved` alone is not the test.** A wave whose ready set is all S routes approves
  nothing by construction and still advances: `blitz_land` parks each S execution-ready, and
  `needs_plan` keys off that stamp (§ Three lanes above says so in as many words). Reading this
  condition as `approved == 0` halts a healthy blitz and reports it as a stall. Measured
  2026-09-10 on project-rag, one fire of a five-fire wave: `approved: 0`, `execution_ready: 2`,
  and a candidate set that still falls — `needs_plan` 27 to 24, `remaining` 18 to 15. Tripwire:
  `AN-ALL-S-WAVE-APPROVES-NOTHING-AND-STILL-ADVANCES`.
  **And it is a WAVE-level test, not a fire-level one.** A wave over 8 is drained by several
  fires sharing one `waveIndex` (§ batching), but `blitz_land` takes ONE fire's result, so the
  landing you are holding is a fraction of the wave. Sum the three lanes across every fire at
  this `waveIndex` before concluding anything. Same wave, same day: one fire of five landed
  `approved: 0`, `closed: 0`, `execution_ready: 0` — genuinely nothing — while the wave around it
  had opened 9. Stopping on that fire would have ended the run at its most productive point.
  **And the test only applies to a wave that FINISHED.** A fire killed part-way — a rate limit, a
  crashed host, a cancelled run — returns the identical zero-lane signature, because a wave that
  never reached its readiness gate has nothing to report in any lane. That is not "it opened
  nothing"; it is "it never ran", and the two want opposite responses: stop versus resume. Check
  completion BEFORE reading the lanes. The tells are in the result and its diagnostics, not in the
  counts: agents that errored, and every `converged` row reading
  `skipped: "no integration report to resolve over"`. **Never land an unfinished fire** — its
  `ready: []` is an absence of judgment, not a judgment of nothing, and stamping it writes that
  absence to disk as a verdict the wave never made. Resume it instead: a Workflow run resumes from
  its own run id and replays every agent that already completed, so recovery costs only the agents
  that died. **A run id resumes only in the session that fired it.** Once that session is gone the
  fire is re-emitted and re-fired, and an XS its trail records as finished is closed with
  `archive-stamp-cli ship-handoff <path> --sha <sha>` — an unfinished fire has no result to land. Measured 2026-09-10 on this repo: four concurrent fires hit one account session limit
  within minutes of each other, and all four returned `ready: []`. A driver reading the lane test
  first would have ended a 200-baton blitz on a transient limit that cleared by itself.
  Tripwire: `AN-UNFINISHED-WAVE-IS-NOT-A-WAVE-THAT-OPENED-NOTHING`.
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

**Host availability on the box the wave runs on is never a pull reason.** The readiness gate asks
whether the plan can be RUN — by whoever runs it, on the host it names — not whether it can be run
here, now, by the gate. A plan whose rows are withheld behind a declared `external_gate` for a host
this box is not is READY, and the withheld rows are a schedule fact, the same way a non-empty
`mise_prepped_findings` is one. Pull for properties of the PLAN: an unapplied finding, an unsettled
escalation whose answer changes the deliverable, self-contradictory acceptance criteria. Tripwires:
`A-PLANNING-GATE-IS-NOT-AN-EXECUTION-GATE`,
`THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON`.

**One reviewer-attributed option is a recommendation, not a choice and not a dead end.** Two or
more contested options are arbitrated by the resolve pass, which picks one; exactly one is applied
or declined with a reason, which is ordinary integration work and not arbitration. Neither lane may
carry an option the integrator composed — the attribution filter drops those before either lane
sees them, and that bound is what the two-option floor protects. A recommendation the pass neither
applied nor declined reconciles a `ready` verdict to `pulled` mechanically, so something decides
every one of them. Tripwire: `A-SINGLE-REVIEWER-OPTION-IS-A-RECOMMENDATION-NOT-A-DEAD-END`.

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

**`approved` is not `mise-prepped`, and a wave never stamps one.** Landing opens the *planning*
gate; the `mise_prepped_by/_at/_sha/_findings` attest says a hands-off run may fire the plan
without an overseer, and it is stamped by `plan.stamp_prepped` outside this skill. This skill
stops at *ready to execute* in both vocabularies.

**A wave's body edits invalidate a stamp; its frontmatter writes do not.** `mise_prepped_sha` is
`canonical_body_sha` of the plan BODY, frontmatter excluded — so `blitz_land`'s `status: approved`
flip, its baton link and its `execution_authorized_*` park all leave an existing stamp intact by
construction. The review-integrator applying findings rewrites the body, and that does invalidate
it: the plan is then STALE, and STALE re-gates rather than re-stamps. Never read
`mise_prepped_by` for presence. Tripwire: `A-PRESENT-MISE-PREPPED-STAMP-IS-NOT-A-CERTIFICATION`;
consumer contract: `coordinator/docs/wiki/mise-prepped-attest.md`.

---

## Repair

The caller builds `repairBatons` — the workflow reads it, never discovers it. One entry per plan
to re-disposition:

```
{ batonId, planPath, reviews: [ <pointer record>, ... ], unresolvedPointers: [ ... ] }
```

**Where the records come from.** A wave has each reviewer provision its findings sidecar through
the `provisionSidecarCli` its caller resolved, and leaves in the trail only a pointer record naming
it:
`{ sidecarPath, verdict, premiseFailure }`. Resolve each pointer under the target plan's
trail directory — RECURSIVELY, and from the latest WAVE slot only. Pointers sit in the per-fire
slot of the wave that wrote them; a `repair-<fireId>/` slot holds an integration report and NO
pointers, because a repair re-emits none — read one as your pointer source and you hand `reviews:
[]` to a baton whose reviews are on disk one directory over, and it refuses. A baton planned in
more than one wave has one set per wave slot, so take the latest wave slot's rather than merging
them. **Latest is by INTEGER wave index, never lexical** — `wave-10-…` sorts before `wave-2-…` as
text; a flat record at the run root predates every slot; `recycle-check.py :: _slot_order` is the
ordering, do not re-derive it. Then partition: a record whose `sidecarPath` still exists on disk goes in
`reviews`; one whose target is gone goes in `unresolvedPointers` as `{ pointerPath, error }`.

**Refusals, all loud, none silent.** Repair refuses the whole baton — it never disposition a
subset — when: no `planPath`; any `unresolvedPointers`; an empty `reviews`; any record missing
`verdict` (the pre-pointer-contract bare-path shape, which would otherwise integrate under a
verdict nobody wrote); or no `trailDir` on the run. Every refusal names the baton and the reason,
because a repair run that quietly clears a plan it found nothing to disposition is indistinguishable
from one that re-dispositioned it.

**What it does not do.** It dispatches no `sizingScout`, no `planner`, no `reviewerAgent`. The one role it
reaches is `integrator()`, unforked, which holds no `Agent`/`Task` tool and so cannot spawn one
transitively. Verdicts resolve through the same `resolveVerdict()` a live wave uses, so a
record carrying a premise failure becomes PIVOT here exactly as it would in a wave, rather than
falling back to BLOCKED.

**Its first repairable input is a wave run after this shipped.** Trails written before the
structured pointer record carry a bare path, not a record, and are refused by the verdict guard
above. Repair does not rescue the backlog that motivated it.

---

## Anti-scope

- Does not author roadmap batons (`coordinator:roadmap-planning`).
- Does not execute plans, and never opens an execution gate. It stops at *ready to execute*.
  **That boundary is not conditional on who reads the exit.** The landing is durable on disk
  (`status: approved`, `governing_plan`), so mise-prep's entry reads it back through
  `roadmap.plan_gate` — a read reports what a gate would say and never opens one. Consumer:
  `skills/plan-blitz/mise-prep-entry.py`. Tripwire: `A-HANDOFF-AN-EM-RETYPES-IS-NOT-A-SEAM`.
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
| 5 | `A-PRESENT-MISE-PREPPED-STAMP-IS-NOT-A-CERTIFICATION` | this file + `skills/review/SKILL.md` | ≥2 | 1 means only the surface that introduced it knows the predicate is a recomputed sha |
| 6 | `THE-BOX-THE-WAVE-RAN-ON-IS-NOT-THE-BOX-THE-PLAN-RUNS-ON` | this file + `agents/blitz-em.md` | ≥2 | the surface that PULLS has to hold the rule; 1 means only the skill describing the gate knows it |
| 7 | `A-SINGLE-REVIEWER-OPTION-IS-A-RECOMMENDATION-NOT-A-DEAD-END` | this file + `agents/blitz-em.md` | ≥2 | the gate reads APPLIED/DECLINED lines it has no vocabulary for otherwise |
| 8 | `AN-ENVELOPE-FROZEN-AS-A-GATE-REPORT-READS-AS-AN-EMPTY-WAVE` | this file + `skills/plan-blitz/recycle-check.py` | ≥2 | the reader that unwraps and the step that tells you to freeze must both carry it; 1 means the code is tolerant and the instruction still teaches the trap |
