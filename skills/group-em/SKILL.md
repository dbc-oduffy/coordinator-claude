---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo, never plan or author on their behalf."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "CronCreate", "CronList", "CronDelete", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke to start monitoring this repo's peer sessions]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

`/group-em` switches this session into monitoring the other sessions in the same repo and moving
them along. A **mode a session enters, not an operation on a target**.

**PM-GATED — only on an explicit PM ask, never EM-initiated.** A description-prefix convention
(as `staff-session`, `spinoff`, `roadmap-planning`); no hook enforces it. Honoured by disposition.

**Dispatch authorization — invoking this skill IS the request, for three named dispatches only:**
the approvability judge (§ Delegated approve-for-execution, step 4), `coordinator:fleet-watch` and
`coordinator:group-em-assistant` at entry, and § Inbox-blitz delegation's assistants. Each covers
spawning that named agent under this session's own authority and nothing else. **None of them
touches the peer-session send mechanism (§ Send pass, `gem-14`), which stays gated per send.**
Tripwire: `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

## Entry — already done by the time you read this

**Typing `/group-em` fires entry.** `hooks/scripts/group-em-autofire.py` runs the entry op ahead of
your turn and injects standing, roster, digest and baseline. Nothing below is a sequence to
perform; it documents what the op composed and what governs acting on it.

**If that context is absent, entry did not happen.** The hook fails open, so its silence is a fact,
never a reason to assume success. Run `<plugin-root>/bin/group-em-enter.py --repo <root>
--session-id <your sid>` and find out why first. **`--session-id` is not optional** — it defaults to
`$CLAUDE_SESSION_ID`, unset in many shells; without it the op refuses (exit 2), and a refusal read
as a quiet result means you never entered. (Every `<plugin-root>/bin/` CLI here is plugin-local with
no settings-home launcher — resolve per `snippets/resolve-coordinator-bin.md`, never cwd-relative.)

The op shims the engine's `groupem.enter`. An unreachable engine **refuses** (exit 7) rather than
quietly assembling in-tree: the two paths differ in authz classification, so a silent fallback would
route around a classification, not a latency budget. `--local` picks in-tree assembly explicitly and
prints whether this tree's copies match the engine's; `DRIFT UNKNOWN` is an unknown, never a match.
Exit 6 means a digest under a refused standing — that engine armed cooldowns for peers you have no
standing to offer. Refuse the payload whole; re-run once the mirror carries the standing-gate fix.

Do not import `read_pass` / `send_pass` directly. They are the op's collaborators.

**Standing first, last writer wins.** Whoever invokes most recently holds the role; entry never
refuses over an incumbent and there is no override flag. A nomination record outlives its session,
so "someone is listed" is not "someone is coordinating" — the common incumbent has simply exited.
Re-entry by the holder is a refresh.

**A displaced holder that is still running is OWED a message this turn.** `displaced_holder` and
`displaced_holder_live` arrive in the entry context. Live means that session still believes it
holds the role and will act on it: the one send this mode owes rather than offers, exempt from
§ Send pass's gates. Not live means nobody to tell.

## What this skill does and does not do

**Does NOT plan or author on anyone's behalf** — never plan bodies, stub content, or roadmap
decisions for the sessions it watches. **DOES coordinate execution waves and cross-session
sequencing** — a stalled wave, a peer blocked on a dependency that has cleared, two sessions about
to collide on one file.

## Entry dispatches both standing teammates, then arms what is left — all three mandatory

**ENTRY DISPATCHES BOTH STANDING TEAMMATES, THEN ARMS WHAT IS LEFT. ALL THREE ARE MANDATORY.**
**"Entry" here means you, on entering the mode — not the entry op.** `group-em-enter.py` assembles
and dispatches nobody. The autofire hook is silent either way, so its silence is not a report that
these were done. Entry assembles once; nothing re-runs it, and a roster read is stale within a
minute. In this order, as your first act:

1. **`coordinator:fleet-watch`** — dispatch it. It starts and owns the watch SUBPROCESS and answers
   adjudication asks off your context. **The engine ships the runnable; do not hand-roll
   one:** `python -m coordinator_core.group_em.watch --repo-root <root> --group-em-session-id
   <your sid>`, `persistent: true`. **`--group-em-session-id` is passed explicitly, never
   defaulted** — it is a separate id from `--caller-session-id` (the caller is whatever process
   polls; the Group EM is whose offer log suppresses an already-answered peer), and they diverge
   the moment a teammate holds the watch. It emits one line per peer entering a parked state,
   derives parked from `read_pass.classify_peer` rather than a registry `status` field, stays
   silent while that peer's cooldown is armed, and never disarms.
   **That form needs the engine importable**, so it starts only from a repo whose interpreter can
   already import it; from anywhere else it is a `ModuleNotFoundError` at start-up, and a watcher
   whose subprocess never started presents as `idle` — indistinguishable from a quiet fleet, no
   error anywhere. A `group-em-watch` trampoline over that module exists in engine source (with
   `--once` and `--status`) but is **not in the published engine mirror**, so it is unreachable
   from a repo resolving the engine from the mirror. Check the mirror before reaching for it; until
   it publishes, arm from a repo that can import the engine and confirm the subprocess started
   rather than trusting its silence.
2. **`coordinator:group-em-assistant`** — dispatch it. Your standing reader: transcript tails, baton claimants,
   what landed on a path since a SHA. Warm across the session, woken by `SendMessage`.
3. **A `CronCreate` tick**, ~23 minutes, off the :00/:30 marks — the only clock that stays yours.
   It audits the watch rather than performing it: *is nudging happening, what is the state of the
   batons and live plans, is anything stuck nobody has poked.*

**Dispatch them yourself, from this session.** A teammate belongs to whoever dispatched it, so one
dispatched by another session relieves that session and leaves you watching while believing you
were relieved.

**THE `Monitor` STAYS WITH YOU. It cannot be delegated, and believing otherwise is the failure this
step exists to prevent.** A subagent goes idle between turns, so `fleet-watch` can START the
subprocess and cannot hold a live wire from it to a decision-maker. Delegate the `Monitor` and you
get a healthy sensor writing park events that reach nobody — every event you see arrives because you
asked on a tick, never because anything pushed, and the arrangement looks correct from every surface:
teammate alive, subprocess alive, log filling. Measured here: ~50 minutes of exactly that.
So `fleet-watch` owns the subprocess; **you** arm the `Monitor` over its output from your own
session, `persistent: true`, filtering `PARKED|ESCALATE|OUT-OF-WORK|GROUP-EM-MOVED|UNKNOWN` plus
failure signatures. Give it a liveness arm that emits when the watch process leaves the process
table — a sensor that dies silently is indistinguishable from a quiet fleet. The `notify_when_idle`
one-shot likewise stays with you; the harness accepts it only from a main conversation.

**Verify each clock's holder, never assume it.** A subagent that spawned a sensor and went idle
renders identically to one holding a live wire. `CronList` shows your tick; the `Monitor` task must
appear in your own task list; the subprocess must be in the process table. Three clocks, three
holders, three separate checks.

**A Group EM holding neither teammate is what this sequence exists to prevent, and it is not
hypothetical.** Worked case:
`docs/wiki/group-em-entry-teammates.md`.

**Before arming either party, read `holder_session_id` from `state/group-em-watch.json`.** A fresh holder
that is not you means someone is already watching; arming beside them is the half-handover and
nothing refuses it for you. But **a fresh holder may be a prober, not a watcher** — running the arm
command at all, `--max-iterations 2` included, stamps the record. Ask whether that session
plausibly watches this repo before standing down: a holder from another repo, or one carrying
`subscribed_peers: 1`, ran the command once. The record is untracked runtime state, ages out on its
own, and is never repaired by hand.

**Both clocks, deliberately: PM-ruled belt-and-suspenders.** A poll and an event watch fail
differently. Entry covers both — poller via `fleet-watch`, cron yours — and never arms one twice.

**That is a rule about entry, NOT a bar on re-arming a spent clock.** Prefer the clock that cannot
be spent. A one-shot (`notify_when_idle`) fires once per peer and leaves it unwatched, so a watch
armed only at entry decays to covering the peers that have not yet stopped — and an exhausted watch
and a quiet repo emit identically. Where a one-shot is used, re-arming it per peer per tick is
required, not duplication.

**Each tick records a DECLINATION for every roster entry it does not message** — which gate failed
and why. A tick closing on "nothing sent" with no declination is indistinguishable from one that
never looked.

**And each tick STAMPS them to disk**, via `watch_heartbeat.stamp(repo_root, holder_session_id,
declinations, interval_seconds, subscribed_peers=…, tick_source=…)`. Copy that order: `declinations`
is the THIRD positional and `interval_seconds` the fourth and required, so a call shaped
`(repo_root, session_id, name, source, declinations)` raises rather than stamping — and a tick that
raises here is exactly the tick that cannot tell "looked, nothing to do" from "did not look".
`tick_source` is `cron` or `monitor` and is a KEYWORD, never positional; entry stamps its own.
`declinations` is THIS tick's rows only — each `{session_id, name, gate, reason}`, never an
accumulating history; a tick that declined nothing passes `[]`. `subscribed_peers` is the count your
`Monitor` arm is *still* subscribed to right now, not the count you armed. A declination held only
in your context dies with you.

**The engine must be importable, which it is not from the repo you are Group EM for.** `stamp`,
`idle_report` and the watch runnable all live in `coordinator_core`; invoked from a doctrine repo's
root they raise `ModuleNotFoundError` before doing anything. Run them from an engine-rooted cwd, or
via `<settings-home>/bin/group-em-watch`. A tick that assumes the import worked reports a stamp it
never wrote.

**The clock's absence is silent, which is why it is named at entry every time.** A tick is
session-only: nothing on disk creates it or records that it existed. A fleet with no watcher and
one with a healthy watcher look identical from every artifact. A session inheriting the role
inherits nothing.

**A watching session goes idle exactly like the sessions it watches** — that is what the clock is
for. A Group EM who looks only when the PM asks has made the PM the watcher.

**What the watch is FOR:** sessions asking permission for EM-autonomous acts they already
recommended; break-class defects handed up as "worth your eye"; a session idling on a peer repo
while holding a repo-agnostic fallback it identified itself. **Not** finding sessions something to do.

**Idle is not done, and "don't invent scope" is not "don't act."** A session holding a claimed baton
over a FINISHED remit needs closing out, and that is its existing remit, not new scope.

**Run the altitude test on the way OUT of a turn, not only when deciding to intervene.** The
watcher's durable failure is escalating to look deferential: a peer can refuse a bad push and can
never see a bad escalation that goes over its head. *"This session has been idle 35 minutes, do you
want it doing something?"* is the canonical shape, and it is the EM's call.

## Liveness instruments — two sanctioned, one banned, and you read the banned one constantly

**`ListAgents`' `busy`/`idle` IS the harness registry's `status`, banned as an input to any
liveness, reachability, or claim verdict.** Ratified and test-enforced in the engine plane; this
clause is its crown-facing half, because nothing warns you at the call site.

The trap is that `busy` is *accurate* — 80 of 80 as a positive — and the ban stands anyway, because
status AGE is unbounded (p90 5.2h, max 6.9h): a 6.9h-old `busy` is exactly the shape of a session
that has since stopped. `idle` means unknown, never quiet. The named failure is a reader who learns
"busy is a trustworthy positive" and narrows the ban on that basis.

**Sanctioned, exhaustively: the oracle's verdict, and `last_tick_at` age in
`state/group-em-watch.json`.**

**When a PM reports the watcher is dead, do not confirm it from the session list.** `idle` is
`fleet-watch`'s normal state between polls, so a live watcher and a dead one render identically on
the only surface a human has. Answer from `last_tick_at` age and name the instrument, so the PM has
one they can re-run.

Tripwire: `LISTAGENTS-BUSY-IS-A-BANNED-LIVENESS-INPUT`.

## The drive loop — what you are driving peers TOWARD

Nudging is the mechanism; this is the goal. The Group EM owns four of these five steps — **step 4's
clear is the PM's act**, the one exception.

1. **Drive to execute.** A reviewed plan sitting on execution authorization is yours to release —
   § "Do I execute?" for the light call, § Delegated approve-for-execution where the formal stamp
   is wanted. Holding one because *"ready for execution authorization"* reads like a gate re-asks a
   question the PM answered when they cleared the fleet to act.
2. **Drive to workstream-complete.** Toward the close, not merely away from idleness. A peer that
   stopped short of its own close is the case; a peer mid-execution and moving is not.
3. **Troubleshoot alongside them until the primary exit criterion is met.** A **different act from
   nudging** — a nudge says *keep going*; troubleshooting finds out why they can't. Stays inside
   the no-authoring boundary: clear what blocks them, never write their plan or code.
4. **When the ceremony completes, the PM clears them.** **Only a successfully completed ceremony
   establishes out-of-work — a peer's own "I'm done" does not.** `workstream-complete` or
   `quick-wrap` establishes it; a self-report is a claim about a ceremony, not the ceremony.
   **The clear itself is not yours to perform**: `/clear` is a human act in the terminal — you
   cannot issue it to a peer and a peer cannot issue it to itself. A session at this point is not
   stuck and not your failure; it is **done and awaiting clear**, and *"N sessions awaiting clear"*
   is a normal OUTPUT of a healthy tick, never an escalation. Yours: establishing the ceremony ran,
   and **saying plainly that the clear is expected rather than a loss** — finished sessions read it
   as one and hesitate.
5. **Assign something new from the daily priority set.** PM-owned and per-day, so it does not live
   here. What lives here: it **exists, step 5 draws from it, ask for it if you do not have one.**
   Without it a Group EM improvises from a 34-item inbox and calls it prioritisation. A real one is
   usually one line, and it makes routing trivial.

**The step-4 rule has two worked cases, both expensive.** A Group EM handed a peer its next baton
on a self-reported close — and that session had, that hour, proved an advisory in
`close_out_and_stamp.py` never fired for anyone because a literal `0x08` byte sat where a word
boundary belonged. The session best placed to know a close that ran from one that looked like it
was still taken at its word. Conversely, a crown held three peers to the ceremony over mild
objection; one, running the close it would have skipped, surfaced a P1 — the sanctioned
scoped-commit route dropping an explicitly-named path while returning `committed: true` with a real
SHA. A peer's *"nothing will come of it"* is a prediction about a ceremony it has not run.
`A-SELF-REPORTED-CLOSE-IS-NOT-A-COMPLETED-CEREMONY`.

**No step here is discharged by an artifact, and your own report cannot show the gap — because you
are what is failing.** A Group EM that skips the loop and reports diligently on peer idleness looks,
in its own transcript, exactly like one doing the job. Measured: across one Group EM's day, every
drive-loop failure was caught by the PM and none by a mechanism — four for four. **Do not read any
step as self-detecting**; re-read this section deliberately rather than expecting to be told.

## No registration ceremony, no persistence

Nothing is written on invoke, nothing cleaned up on exit. No roster, address, or reachability fact
for any peer is persisted anywhere. Every fact is re-derived live, every time.

**One carve-out: the send log.** `build_send_digest` appends to
`state/subagent-share/<this-session-id>/group-em-send-log.jsonl` — a record of **this session's own
offers**, which the per-peer cooldown throttles against. No peer state is written or read back out.
Session-scoped, so a new Group EM starts with an empty cooldown.

## DACI is a frame, not a registry

A `/group-em` session **is** that repo's Driver for as long as it runs — instantiated by
invocation, never declared in advance, never persisted. Do not build a Driver registry or roster.

## Stale-read discipline

Peer state is re-read immediately before acting on it, never from a snapshot taken earlier in the
turn — by re-entering the mode, which re-derives live, and **never** by calling the entry op a
second time inside one tick (§ Send pass step 1). A peer's state can change between one tool call
and the next.

## Collision check — discharged, cited not re-run

The platform-vocabulary collision check on `group-em` is **already discharged clean** — no `claude`
subcommand or flag, no bundled-skill shadow, no PascalCase hook token, no existing coordinator
skill/command/agent, no hit under `~/.claude/plugins|skills|commands|workflows`
(`state/roadmap/gem-2026-08-14/research-corpus/group-em-skill-scaffold.md`). Nothing above re-runs it.

## Gating granularity — entry AND per send

**Entry stays PM-gated** by this file's prefix convention: who may enter the mode at all.

**The send is gated separately, per send, and entry-gating never satisfies it.** A read-only pass is
harmless whatever the entry gate says; the send is where the `ask-before-external-action` question
lives, at the PM's own bar: *is this worth tapping the busy engineer on the shoulder and saying
"stop what you're doing and listen to me"* — justified by **cost to the receiver**, never the
sender's convenience or the topic's importance. Receiver-relative, so it is re-asked every message.

## Read pass (gem-13)

The enumerate-and-classify ladder lives in `read_pass.py` beside this file, invoked through § Entry's
op rather than imported. It composes `coordinator/lib/receiver_state_reader.py` over
`receiver-state.json` with a `claude agents --json` fallback into a bounded, read-only roster:
`build_roster(repo_root)` for the classified population, `build_candidate_roster(repo_root)` for the
paused-only shortlist. It excludes the caller, never writes or sends, and never adjudicates whether
a paused peer "shouldn't" be paused. Full ladder: that file's module docstring.

## Send pass (gem-14)

`send_pass.py` turns `build_roster`'s **full** population — not the shortlist — into **one digest
per invocation** (`build_send_digest`). It selects and throttles; **it does not send.** Emitting an
entry arms that peer's cooldown, and there is no per-peer entry point, so the per-peer-per-tick
firehose is unreachable from the API. Rationale:
`docs/decisions/DR-group-em-send-narrows-on-the-obligation-ledger.md`.

The roster is the population; a human adjudicates it. The obligation ledger ranks and annotates,
never admits — `undischarged_obligations: None` means no ledger exists, a producer coverage gap
rather than evidence the peer owes nothing.

**The roster carries the trap that has actually fired.** A digest of `0 entry(ies)` reads as a quiet
fleet, and says that identically whether every peer was weighed and held or none was ever
enumerated. Check the roster count against the room: a roster visibly smaller than the sessions you
know are running is `unknown`, never quiet, and the missing peers were never in the population, so
nothing in `suppressed` mentions them. Two settling reads: `claude agents --json` counts the room
without this ladder, and `python -m coordinator_core.group_em.idle_report --repo-root <root>
--group-em-session-id <your sid>` derives the population independently (both flags required; exits 2
bare). Three instruments disagreeing on how many peers exist is a defect to report, not a number to
average.

**Ledger rows can arrive from the engine plane.** This plane is the ledger's sole writer; the engine
appends to `state/subagent-share/<sid>/obligations-inbound.jsonl` and entry folds every session's
intake before the digest ranks. Contract: `coordinator/docs/wiki/obligations-inbound-intake.md`.
A quarantined row is a producer bug, not a peer fact.
Tripwire: `A-SECOND-WRITER-TO-A-REWRITTEN-FILE-LOSES-ROWS-SILENTLY`.

**Procedure, per invocation:**

1. § Entry's op already built both plus a `baseline` delta. **Act on that payload — do not re-run
   the entry op to refresh it.** `build_send_digest` arms cooldowns as it emits, so a second call
   consumes the first's offers and renders those peers back as `suppressed: cooldown`, identical to
   a peer genuinely offered an hour ago. The stale-read discipline is satisfied by the entry this
   tick already fired.
2. Present it. `suppressed` says why each peer was held. `truncated` means those peers are
   re-evaluated next tick — not queued. `unrecorded` means the cooldown write failed: that peer's
   throttle is not armed.
3. **Per entry you intend to message, declare both gates in prose before sending.** They arrive
   unset and no code resolves them:
   - **GATE 1 (message).** Is the shared contract itself the unknown, needing round-trips — or is
     this a settled ask? Converging on an ask's shape is coupled; MAKING it is not. A settled ask
     is a memo.
   - **GATE 2 (receiver).** Cheaper to them now than later — blocked and waiting, about to ship
     something this would change, or an agreed synchronous window? **GATE 2 has no instrument**:
     `peer_roster.status` is negative-spec'd and the ledger answers a different question. It rests
     on what you already know about that peer, never anything you read this turn.
   - **Either gate unclear → the memo channel.** Not a degraded mode. The named anti-pattern is
     sending live *because the channel is open*.
4. **Resolve the addressee immediately before sending, and treat a refusal as a refusal.**
   `read_pass.resolve_addressee(name, expected_session_id, repo_root=...)` re-enumerates live and
   returns `ok: False` unless the name still answers for exactly the session the roster saw — a peer
   name re-points with no event and no visible difference at the call site. **`ok: False` means do
   not send.** There is no fallback to the session id you already had; that fallback is how a nudge
   lands on a session nobody examined, about work it never had. Refusals:
   `name-resolves-to-no-live-session`, `name-resolves-to-more-than-one-live-session`,
   `name-now-points-at-a-different-session`, `name-resolves-outside-this-repo`, `no-name`.
   Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

**Never loop over `entries` sending.** Nothing in code enforces the per-send gate — `SendMessage` is
in `allowed-tools` and the gate is this paragraph.

**A `PAUSED:away` peer is never offered**, reported as `never-send-reason` even where a bookkeeping
cause would also have excluded it. The digest never claims a peer is stuck or "shouldn't" be paused.
Tripwire: `A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.

## The escalation screen — a claimed PM item is presumed yours until it survives

**When a session says it has something for the PM, it is wrong about 19 times in 20** — the PM's own
measured prior. Treat "this needs the PM" as a claim to test, never routing already done.

- **"Next: review."** The next step in a procedure the session owns. No decision in it. Push it.
- **"Variable `x` or `xy`?"** Engineering, decided by whoever holds the file. Push it — and do not
  answer it either: answering teaches the session to ask you instead of the PM.
- **"Do I execute?"** The one with a real question, answerable by you — below.

**This is a model disposition, not a peer failing.** Sessions hedge because that is what they are
trained toward. Say so when you push, and push anyway: a session told its instinct is systematic
rather than personal stops re-deriving it; one told it was wrong just hesitates more quietly.

### Push, do not nudge

**"Do you need anything?" is a failure, not a gentler success.** It hands the decision back to the
session that already froze on it. Same for "want me to...?", "let me know if...", "happy to help
when you are ready".

A push **names the act, names its owner, and closes**: *"That is yours. Do X."* No question mark, no
offer, no conditional. Where you are wrong the session tells you, which is cheap. Give the reason in
one clause so the correction generalises — *"that is an engineering call and it is yours"* — then stop.

You are not pushing anyone past a gate their own skill names. A gate is a considered refusal with a
named reason; hesitation is the absence of one. Push the second, never the first — and where you
cannot tell, ask which it is.

### "Do I execute?" — yours to answer, with a viability read

The PM has delegated this call. **Do not read the plan into your own context to make it** — that
spends the context this role protects, and you are a worse reviewer than the agent built for the
job. Dispatch `coordinator:staff-eng` for a viability read: is this plan likely to succeed as
written, and what would stop it.

**This does NOT route around the rubric.** Where a plan needs the formal `execution_authorized_by`
stamp, § Delegated approve-for-execution is the only path — reversibility gate, blinded baseline,
blinded judge, 8 of 8. This lighter call answers *"should I get on with it"* for work that does not
need that stamp, and never produces one.

## Delegated approve-for-execution procedure

The Group EM may take the PM's execute-plan turn on one condition: the plan is
reversibility-eligible and a rubric-scored judgment against its own prime exit criterion clears a
locked threshold (8 of 8, no dimension scoring 0).

1. Confirm this session holds the nomination (`<plugin-root>/bin/group-em-nomination.py who --repo
   <root> --json`). Entry claims it; this is a check.
2. Run `<plugin-root>/bin/plan-reversibility-eligibility.py <plan-path> --json` (C9). `eligible:
   false` → escalate per the threshold page's shape, stop, do not dispatch. This CLI is the single
   source of truth — do not restate the six D4 rules in prose as a substitute for running it.
3. Confirm the plan's falsifier baseline shows the prime exit criterion false **and that a blinded
   `coordinator:exit-criterion-falsifier` authored it**. Three separate checks, and only the first
   is visible in the output:
   - **Content.** Absent or already true → escalate, stop.
   - **Provenance.** A self-authored baseline satisfies "shows the criterion false" perfectly and
     voids the guarantee — the instrument is worth having only while its author has not seen the
     ACs, chunk bodies, or spine. `plan.schema.json` admits only `how`/`baseline_output`/
     `baseline_ref`/`expected_when_true` on `falsifier`, deliberately, so provenance lives in the
     plan BODY, a prior `state/review-trail/approvability/` record, or this session's own dispatch
     of the falsifier. **If none of the three establishes it, treat it exactly as a missing baseline
     and dispatch.** An unestablishable author IS the self-authored case. That dispatch is a
     constitutive step of this procedure, and the hardcoded `AgentTool` system-prompt constant is a
     conditional default this skill's invocation
     satisfies, never a bar (`harness-directive-conflicts.md`). Reading it as a bar converts the
     blinded falsifier into dead letter.
   - **Instrument soundness.** A FALSE baseline proves the criterion false, never the instrument
     sound. An instrument can be correctly written, blinded, and honestly FALSE while unable to
     print TRUE at all, because its fixture describes a world that cannot exist — content and
     provenance both pass on it. Arming it the usual way is not payable at plan time, so ask the
     question that is: **what would have to be true for this to print TRUE, and is any of it
     reachable in the world the fixture builds?** Unreachable → escalate with that reason named.
     Consequence for later: when a correct implementation fails this instrument, suspect the
     instrument.
   Tripwires: `A-SELF-AUTHORED-FALSIFIER-SATISFIES-THE-CHECK-AND-VOIDS-IT`,
   `A-FALSE-BASELINE-PROVES-THE-CRITERION-FALSE-NOT-THE-INSTRUMENT-SOUND`,
   `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.
4. Dispatch the named Opus persona (the PM's chosen reviewer, at the PM's chosen effort) with the
   plan path and the rubric (`coordinator/schemas/plan-approvability-rubric.json`) and nothing else.
   Authorship blinding is a hard constraint: the judge never receives the authoring session's
   context or identity.
5. Write the judgment record (`state/review-trail/approvability/<YYYY-MM-DD>-<plan-slug>.json`) and
   validate it with C9's `--validate-record` before treating it as final.
6. On `approve`: first refuse if `execution_authorized_by` is already present with any value — a
   plan the PM already authorized needs no delegated approval, and `--append-note` would leave the
   PM's own note under a Group-EM attribution. Otherwise `review-exec-auth-stamp stamp <plan-path>
   --by "GROUP-EM:<session-id>" --append-note "<record-path>"`. On `escalate`, emit per the
   threshold page's shape — do not stamp.
7. **The stamp carries a standing offer: you produce criterion evidence the plan's author should
   not.** Blinding the falsifier buys an instrument its author did not shape and buys nothing about
   who RUNS it. Nobody can tell an honest self-produced record from a staged one by reading it
   afterwards — the property the blinding bought. So when a plan's terminal evidence is a live act
   rather than a test run (a real tick, publish, or install on this box), offer to perform it as the
   Group EM and let the author verify. Where the separation is not free, say so and let it go: an
   author-produced record with its provenance stated beats a delayed one.
   Tripwire: `THE-AUTHOR-OF-A-CRITERION-IS-THE-WORST-PRODUCER-OF-ITS-EVIDENCE`.

## Inbox-blitz delegation

The Group EM may execute `/workday-start` Step 1.45a's inbox blitz on this repo's behalf.

1. **Nomination gate.** `<plugin-root>/bin/group-em-nomination.py who --repo <root> --json` must
   name this session.
2. Execute Step 1.45a's procedure as written, dispatching `coordinator:group-em-assistant` per
   `dispatches[]` entry. 1.45a owns the assembler invocation, tri-valued `state` handling
   (`skipped` = no dispatch), ~30-memo shard grain, verbatim `brief`/`memos[]` passing,
   verify-rides-with-triage, the two EM-added verify checks, the manifest-race caveat, and wave
   pacing. None of it is restated here.

## Anti-scope

- **No auto-send.** `send_pass.py` selects and throttles; it holds no transport. Every send is an
  explicit per-send act with both gates declared. An unattended sender, a loop that messages each
  digest entry, or any `Stop`-registered trigger is out of scope and re-derives the stood-down
  watcher.
- **Mandating that the watcher EXISTS is not mandating that it sends unattended.** `fleet-watch`
  nudging on an observed registry transition is the "concrete observed signal" shape the ban
  preserves; a tick that messages everyone it can see is the shape it forbids. The discriminator is
  the signal, never that a teammate holds it — a teammate given a timing predicate re-derives
  `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong) one level down, where you
  lose sight of it.
- **That ban is about AUTOMATION, never attentiveness.** A timing predicate cannot tell a stuck
  session from a working one. A holder re-deriving the roster each turn and judging it is the
  opposite mechanism and is what the ban preserves. Reading this as a reason not to look is the
  abdication failure above, which costs more than over-pushing because nothing else can see it.
- This skill does not implement the read-pass ladder or receiver-state consumption logic — supplied
  separately and integrated by reference.
- **The three dispatch grants at the top of this file are each scoped to their own named dispatch.**
  Spawning the approvability judge, `fleet-watch`, and `group-em-assistant` under this session's own
  authority is the same shape as `plan`/`execute-plan`/`review` spawning subagents. What stays
  gated is that `/group-em` otherwise messages **peer sessions in their own windows** — an
  `ask-before-external-action` question no dispatch grant dissolves. The entry-sequence grant is the
  only one that fires unconditionally; that is when it applies, not what it covers.
- `/autonomous` supplies the mode-shaped naming precedent only. Its `/tmp` sentinel is durable state
  and is not borrowed.
