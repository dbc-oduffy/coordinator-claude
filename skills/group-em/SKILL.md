---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo, never plan or author on their behalf."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "CronCreate", "CronList", "CronDelete", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke to start monitoring this repo's peer sessions]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

Invoking `/group-em` switches this session into monitoring the other sessions running in the same
repo and moving them along. It is a **mode a session enters, not an operation on a target** — the
same shape as `/autonomous`'s toggle-a-disposition naming, borrowed for the name only (see
Anti-Scope below; the sentinel-file mechanism does not transfer).

**PM-GATED. Only invoke when the PM explicitly asks for it, never EM-initiated on its own
judgment.** This is a description-prefix convention, matching `staff-session`, `spinoff`, and
`roadmap-planning` — there is no hook or lib that enforces PM-gating anywhere in this repo
(`grep -rln "PM-GATED|pm_gated" coordinator/hooks/scripts coordinator/lib` returns nothing). The
gate is honoured by disposition, not by a guard, until something else supplies enforcement.

**Dispatch authorization — invoking this skill IS the request, for the approvability-judge
dispatch specifically.** The approvability-judge dispatch in § Delegated approve-for-execution
procedure below is a constitutive step of that procedure, not a separate thing to get cleared:
invoking a skill requests the actions that skill performs. This is a narrow grant, not a general
dispatch grant for this skill — it covers spawning the named Opus persona under this session's own
authority for that one procedure, nothing else. It does not touch the peer-session send/nudge
mechanism (`gem-14`, § Send pass (gem-14), gated separately) — that remains outside this
paragraph's scope; see the Anti-scope carve-out below for how the two are distinguished. Tripwire:
`UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.

## Entry — already done by the time you read this

**Typing `/group-em` fires entry.** `hooks/scripts/group-em-autofire.py` runs the entry op ahead of
your turn and injects the crown verdict, roster, digest and baseline as context. There is no
command to run and no step to assemble: the passes below document what the entry op composes and
what governs acting on its output, not a sequence to perform.

**If that context is absent, entry did not happen.** The hook fails open — any failure degrades to
silence rather than blocking your prompt — so its absence is a fact, never a reason to assume it
worked. Run `<plugin-root>/bin/group-em-enter.py --repo <root>` yourself and find out why before
acting as this repo's Group EM.
(Every `<plugin-root>/bin/` CLI on this page is plugin-local and has no settings-home launcher —
resolve per `snippets/resolve-coordinator-bin.md` § CLIs with no launcher; never cwd-relative.)

The op is a shim over the engine's `groupem.enter`, which reads the harness registry in-process. An
unreachable engine **refuses** (exit 7); it never quietly assembles in-tree instead. The two paths
differ in authz classification — `groupem.enter` is MUTATING in the engine registry, the in-tree
passes are unclassified script calls — so a silent fallback would route around a classification,
not merely a latency budget. `--local` selects in-tree assembly explicitly when you mean it, and prints whether this tree's
copies still match the engine's — a divergent ladder answers differently rather than failing, and
`--local` is chosen during an outage, when that is hardest to notice. `DRIFT UNKNOWN` is an
unknown, never a match.

Exit 6 means the engine returned a digest under a refused crown: that engine composes its legs
independently and has already armed cooldowns for peers this session has no standing to offer.
The payload is refused whole. Re-run once the engine mirror carries the crown-gate fix.

Do not import `read_pass` or `send_pass` directly. They are the entry op's collaborators; reaching
past it means supplying your own session id and re-deriving state the op already holds.

**Crown first, and last writer wins.** Whoever invokes `/group-em` most recently holds the role.
Entry never refuses over an incumbent and there is no override flag to reach for — a nomination
record outlives the session that earned it, so "someone is listed" is not "someone is
coordinating," and the overwhelmingly common incumbent is a session that has simply exited.
Re-entry by the holder itself is a refresh, displacing nobody.

**A displaced holder that is still running is OWED a message, this turn.** `displaced_holder` and
`displaced_holder_live` arrive in the entry context. Live means that session believes it is this
repo's Group EM and will act on it; that is the one send this mode owes rather than offers, and
it does not wait on the § Send pass (gem-14) gates — those weigh an interrupt against its cost to
the receiver, and a peer acting under a role it has already lost is not a case where the answer
is in doubt. Not live means nobody to tell. A refusal that still reaches you after entry vacated the
record is not a crown-ownership problem; do not treat it as one.

## What this skill does and does not do

**Does NOT plan — never plan or author on anyone's behalf.** Reading peer state and nudging a
stuck session is never authoring roadmap or plan content for the sessions it watches. A
`/group-em` session never writes plan bodies, stub content, or roadmap decisions on their behalf —
that stays each session's own.

**DOES coordinate execution waves and cross-session sequencing.** The affirmative half of the same
boundary: noticing a wave is stalled, a session is blocked on a dependency that has since cleared,
or two sessions are about to collide on the same file, and nudging accordingly.

**ENTRY DISPATCHES BOTH STANDING TEAMMATES, THEN ARMS WHAT IS LEFT. ALL THREE ARE MANDATORY.**
Entry assembles once. Nothing re-runs it, no hook fires it again, and a roster read is stale within
a minute — so a mode entered and never re-derived reports the room as it was, not as it is. In this
order, as your first act:

1. **`coordinator:fleet-watch`** — dispatch it. It holds the `Monitor` poller over the session
   registry and pokes stopped sessions along, off your context. **The engine ships the runnable; it
   does not hand-roll one:** `python -m coordinator_core.group_em.watch --repo-root <root>
   --crown-session-id <your sid>`, `persistent: true`. **`--crown-session-id` is passed explicitly,
   never defaulted** — it is a separate id from `--caller-session-id` on purpose (the caller is
   whatever process polls; the crown is whose offer log suppresses an already-answered peer), and
   they diverge the moment a teammate holds the watch. That form needs the engine importable; there
   is no settings-home `group-em-watch` launcher yet. It emits one line per peer entering a parked
   state, derives parked from `read_pass.classify_peer` rather than a registry `status` field, and
   stays silent while that peer's send-pass offer cooldown is armed. It never disarms, so there is
   nothing to re-arm.
2. **`coordinator:group-em-assistant`** — dispatch it. Your standing reader: transcript tails,
   baton claimants, what landed on a path since a SHA. Warm across the session, woken by
   `SendMessage`.
3. **A `CronCreate` tick**, ~23 minutes, off the :00/:30 marks — the only clock that stays yours.
   It audits the watch rather than performing it: *is nudging actually happening, what is the state
   of the batons and the live plans, is anything stuck that nobody has poked.*

**Dispatch them yourself, from this session.** A teammate belongs to whoever dispatched it, so one
dispatched by any other session relieves that session instead and leaves you watching while
believing you were relieved. What transfers to `fleet-watch` is the `Monitor` poller; the
`notify_when_idle` one-shot stays with you either way, because the harness accepts that parameter
only from a main conversation and a teammate cannot hold it.

**A crown holding neither teammate is what this sequence exists to prevent, and it is not
hypothetical** — until entry named them, nothing did, and both agent bodies claim to be "kept for
the life of their session" while no step created one. Worked case:
`docs/wiki/group-em-crown-entry-teammates.md`.

**Dispatch authorization — invoking this skill IS the request, for these two dispatches.** Steps 1
and 2 — `coordinator:fleet-watch` and `coordinator:group-em-assistant` — are constitutive steps of
entry, not a separate thing to get cleared, on the same basis as the approvability-judge dispatch
above and § Inbox-blitz delegation's. Narrow, as those are: it covers spawning those two named
agents under this session's own authority at entry and nothing else, and it does not touch the
peer-session send/nudge mechanism (§ Send pass (gem-14)), which stays gated per-send.

**Before arming either party, read `holder_session_id` out of `state/group-em-watch.json`.** The
watch stamps that file every tick, so a fresh holder that is not you means someone is already
watching this repo — arming beside them is the half-handover, and nothing refuses it for you. A
stale or absent holder is the clear case. This is a check you perform; the engine detects the
condition but does not yet prevent it.

**A fresh holder may be a prober, not a watcher.** Running the arm command at all — including
`--max-iterations 2` to check that it works — stamps the record and names the probing session as
holder. So ask whether that session is plausibly watching this repo before standing down: a
holder from another repo, or one carrying `subscribed_peers: 1`, ran the command once. The record
is untracked runtime state and ages out on its own; never repair it by hand.

**Both clocks, deliberately: belt-and-suspenders, PM-ruled.** A poll and an event watch fail
differently, and whichever survives a given interval catches what the other missed. Shipping one is
the elegant choice and the wrong one. Entry covers both in one pass — the poller via `fleet-watch`,
the cron yours — and never arms the same clock twice.

**That is a rule about entry, and it is NOT a bar on re-arming a clock that has been spent.**
Prefer the clock that cannot be spent. A one-shot subscription — `notify_when_idle` is one —
fires once for a peer and leaves that peer unwatched, so a watch armed only at entry decays
during the session to covering just the peers that have not yet stopped, and an exhausted watch
and a quiet repo emit identically. A poller has no such state and is the better default for that
reason. Where a one-shot is used at all, re-arming it per peer per tick is required, not
duplication. Reported by `claude-klabauter-ad` from a live case: a handoff recording eight watched
peers, last re-armed at 00:26, whose watch covered nobody by the time the role was picked up.

**Each tick records a DECLINATION for every roster entry it does not message** — which gate failed
and why. A tick that closes on "nothing sent" with no declination is indistinguishable from a tick
that never looked, which is the failure this whole mechanism exists to end.

**And each tick STAMPS those declinations to disk**, via
`watch_heartbeat.stamp(repo_root, session_id, name, source, declinations, subscribed_peers=…)` —
`source` is `cron` or `monitor` for a clock tick; entry stamps its own. `subscribed_peers` is the
count of peers your `Monitor` arm is *still* subscribed to right now, not the count you armed:
`notify_when_idle` is one-shot and unwatches per peer as it fires, so a watch that armed eleven
peers and has since decayed to zero is not a watch, and only a live count says so. A declination
recorded in your own context and nowhere else dies with you.

**The clock's absence is silent, which is why it is named at entry every time.** A tick is
session-only: nothing on disk creates it, nothing records that it existed, and it dies with the
session that armed it. A fleet with no watcher and a fleet with a healthy one look identical from
every artifact — no error, no gap, no stale marker. So whoever holds the crown re-arms it
themselves, and a session that inherits the role inherits nothing.

**A watching session goes idle exactly like the sessions it watches.** That is what the clock is
for. A Group EM who looks only when the PM asks has made the PM the watcher, which is the whole
thing the role exists to stop.

**What the watch is FOR.** Sessions asking permission for EM-autonomous acts they have already
recommended; break-class defects handed up as "worth your eye"; a session idling on a peer repo
while holding a repo-agnostic fallback it identified itself. **Not** finding sessions something to
do.

**Idle is not the same as done, and "don't invent scope" is not "don't act."** A session holding a
claimed baton over a FINISHED remit needs closing out, and closing out is its existing remit rather
than new scope. Over-applying the no-manufactured-work rule turns it into a reason not to finish
work that already exists — the failure that reads as restraint and is abdication.

**Run the altitude test on the way OUT of a turn, not only when deciding to intervene.** The
watcher's most durable failure is escalating to look deferential: a peer can see a bad push and
refuse it, and can never see a bad escalation that goes over its head. *"This session has been idle
35 minutes, do you want it doing something?"* is the canonical shape, and it is the EM's call.

## No registration ceremony, no persistence

Nothing is written to disk on invoke. Nothing is cleaned up on exit. No roster, address, or
reachability fact for any peer session is persisted anywhere — not in this repo's state
directories, not in a scratch file, not in a sentinel. Every fact this skill acts on is re-derived
live, every time, from the tools available at invocation (`Read`, `Bash`, `Glob`, `Grep` against
this repo's own working state).

**One carve-out, by name: the send log.** `build_send_digest` appends to
`state/subagent-share/<this-session-id>/group-em-send-log.jsonl` — a record of **this session's own
offers**, which is what the per-peer cooldown throttles against. It is not a peer fact: no peer
state, address, or reachability is written, and nothing about a peer is read back out of it. It
follows the existing per-session bookkeeping convention beside
`advisory-fire-counts.jsonl`, and it is session-scoped, so a new Group EM starts with an empty
cooldown — the same lifetime the DACI ruling above gives the Driver role.

## DACI is a frame, not a registry

A `/group-em` session invoked by the PM in a repo **is** that repo's Driver for the sessions it
coordinates, for exactly as long as it keeps running. That role is instantiated by invocation —
never declared in advance, never persisted. When the session exits, the Driver role ends with it;
nothing records that it ever held it. Do not build a Driver registry, roster file, or any standing
record of who is coordinating whom.

## Stale-read discipline

Peer state must be re-read immediately before acting on it, never from a snapshot taken earlier in
the same turn — by re-entering the mode, which re-derives live, and never by calling the entry op a
second time inside one tick (§ Send pass step 1: the second call eats the first one's offers). A peer session's status can change between one tool call and the next; treating an
earlier read as still current is exactly the failure mode this clause exists to prevent. Every
nudge or wave decision re-reads first.

## Collision check — discharged, cited not re-run

The platform-vocabulary collision check on the name `group-em` (plan skill scaffold checklist item
6, `coordinator/skills/plan/residue/plan-corpus.md:53`) is **already discharged clean** — no
`claude` CLI subcommand or flag, no bundled-skill shadow-set collision, no PascalCase hook token,
no existing coordinator skill/command/agent, and no hit anywhere under
`~/.claude/plugins|skills|commands|workflows` (`state/roadmap/gem-2026-08-14/research-corpus/group-em-skill-scaffold.md`
§ "The outstanding collision check"). This citation is the record of that discharge; nothing above
re-runs it.

## Gating granularity — entry AND per send, resolved by `gem-14`

Both, at different strengths, and the send gate is the load-bearing one.

**Entry stays PM-gated** by this file's prefix convention, unchanged — that gate is about who may
put a session into this mode at all.

**The send is gated separately, per send, and entry-gating never satisfies it.** A read-only pass
is harmless whatever the entry gate says; the send is where the
`ask-before-external-action`-shaped question actually lives, and it is where the PM's own bar
applies: *is this worth tapping the busy engineer on the shoulder and saying "stop what you're
doing and listen to me"* — an interrupt is justified by its **cost to the receiver**, never by the
sender's convenience or the topic's importance. Because that bar is receiver-relative it must be
re-asked for every message; one clearance at invocation cannot stand in for it, and receiver state
goes stale on the minute scale in any case.

## Read pass (gem-13)

The enumerate-and-classify ladder referenced in the Anti-scope entry below lives in
`read_pass.py`, beside this file — not inlined here, and invoked through § Entry's op rather than
imported. It composes `gem-11`'s
`coordinator/lib/receiver_state_reader.py` reader over `receiver-state.json` with a
`claude agents --json` fallback into a bounded, read-only candidate roster:
`build_candidate_roster(repo_root)`. It excludes the caller's
own session, never writes or sends anything, and never adjudicates whether a paused peer
"shouldn't" be paused — see that file's module docstring for the full ladder and the measured
reader/fallback split. The send/nudge mechanism that plugs into this roster is `gem-14`,
gated separately — see § Send pass (gem-14) below.

## Send pass (gem-14)

`send_pass.py` turns `read_pass.build_candidate_roster`'s output into **one digest per invocation**
(`build_send_digest`). It selects and throttles; **it does not send.** Emitting an entry arms that
peer's cooldown itself and there is no per-peer entry point, so the per-peer-per-tick firehose is
unreachable from the API rather than left to the sender's memory. Rationale and measurements:
`docs/decisions/DR-group-em-send-narrows-on-the-obligation-ledger.md`.

The roster is the population; a human adjudicates it. The obligation ledger ranks and annotates,
never admits — `undischarged_obligations: None` means no ledger exists at all, a producer coverage
gap rather than evidence the peer owes nothing.

**Ledger rows can arrive from the engine plane.** DoE is the ledger's sole writer; the engine
appends to `state/subagent-share/<sid>/obligations-inbound.jsonl` and entry folds every session's
intake before the digest ranks. Contract: `coordinator/docs/wiki/obligations-inbound-intake.md`.
A quarantined row is a producer bug and entry says so; it is not a peer fact.
Tripwire: `A-SECOND-WRITER-TO-A-REWRITTEN-FILE-LOSES-ROWS-SILENTLY`.

**Procedure, per invocation:**

1. § Entry's op has already built both, plus a `baseline` peer-set delta. **Act on that payload —
   do not re-run the entry op to refresh it.** `build_send_digest` arms each emitted peer's
   cooldown as it emits, so a second entry call consumes the offers the first one made and renders
   those same peers back as `suppressed: cooldown` — identical to a peer genuinely offered an hour
   ago. Re-reading to satisfy the stale-read discipline is the move that hides the peer you were
   about to act on. The discipline is satisfied by the entry the tick already fired: it re-derives
   live and caches nothing.
2. Present it. `suppressed` says why each roster peer was held. `truncated` means those peers are
   not in this digest and are re-evaluated next tick — they are not queued. Anything in `unrecorded`
   had its cooldown write fail: that peer's throttle is not armed.
3. **Per entry you intend to message, declare both gates in prose before sending.** Entries arrive
   with `gate1`/`gate2` unset and no code resolves them:
   - **GATE 1 (message).** Is the shared contract itself the unknown, needing round-trips — or is
     this a settled ask? Converging on the shape of an ask is coupled; MAKING the ask is not. A
     settled ask is a memo.
   - **GATE 2 (receiver).** Is this cheaper to them now than later — blocked and waiting, about to
     ship something this would change, or an agreed synchronous window? **GATE 2 has no
     instrument**: `peer_roster.status` is negative-spec'd, and the obligation ledger answers a
     different question. It rests on what you already know about that peer, never on anything you
     read this turn.
   - **Either gate unclear → the memo channel.** Not a degraded mode. The named anti-pattern is
     sending live *because the channel is open*.

4. **Resolve the addressee immediately before you send, and treat a refusal as a refusal.**
   `read_pass.resolve_addressee(name, expected_session_id, repo_root=...)` re-enumerates live and
   returns `ok: False` with a named reason unless the name still answers for exactly the session
   the roster saw. A peer name is not a stable address — it re-points with no event and no visible
   difference at the call site. **`ok: False` means do not send.** There is no fallback to the
   session id you already had; that fallback is precisely how a nudge lands on a session nobody
   examined, about work it never had, while the sender believes the address held. The refusals are
   `name-resolves-to-no-live-session`, `name-resolves-to-more-than-one-live-session`,
   `name-now-points-at-a-different-session`, `name-resolves-outside-this-repo`, `no-name`.
   Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

**Never loop over `entries` sending.** The per-send gate separates "may be offered" from
"message", and nothing in code enforces it — `SendMessage` is in `allowed-tools` and the gate is
this paragraph. The DR records that as a known limit.

**A `PAUSED:away` peer is never offered**, reported as `never-send-reason` even where a bookkeeping
cause would also have excluded it. The digest never claims a peer is stuck or "shouldn't" be
paused — that population is unmeasurable by PM ruling.
Tripwire: `A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.

## The escalation screen — a claimed PM item is presumed yours until it survives

**When a session says it has something for the PM, it is wrong about 19 times in 20.** That is the
measured prior the PM states, and it is the number this screen exists to act on. Treat "this needs
the PM" as a claim to be tested, never as routing already done.

The three that arrive most often, and what each actually is:

- **"Next: review."** A statement of the next step in a procedure the session already owns. There
  is no decision in it. Push it.
- **"Variable `x` or `xy`?"** Naming, shape, structure — engineering, decided by whoever is
  holding the file. Push it, and do not answer it either: answering teaches the session to ask you
  next time instead of the PM, which relocates the problem rather than closing it.
- **"Do I execute?"** The one with a real question inside it, answerable by you — see below.

**This is a model disposition, not a peer failing.** Sessions hedge, defer, and wait for a human
because that is what they are trained toward, not because they lack judgment or standing. Say so
when you push, and push anyway. A session that is told its instinct is systematic rather than
personal stops re-deriving the same hesitation next time; one that is told it was wrong just
hesitates more quietly.

### Push, do not nudge

**"Do you need anything?" is a failure, not a gentler success.** It hands the decision back to the
session that already froze on it, and its most likely answer is another hedge. Same for "want me
to...?", "let me know if...", and "happy to help when you are ready" — every one of them is an
invitation to keep waiting, phrased politely.

A push **names the act, names its owner, and closes**: *"That is yours. Do X."* No question mark,
no offer, no conditional. Where you are wrong the session tells you, which is cheap; where you are
right it moves, which is the point. Give the reason in one clause so the correction generalises —
*"that is an engineering call and it is yours"* — then stop.

You are not pushing anyone past a gate their own skill names (§ Send pass, and the standing rule
that a peer's refusal is a safety mechanism). Those are different things: a gate is a considered
refusal with a named reason, and hesitation is the absence of one. Push the second, never the
first — and where you cannot tell which you are looking at, ask which it is, because that question
has a real answer.

### "Do I execute?" — yours to answer, with a viability read

The PM has delegated this call. **Do not read the plan into your own context to make it** — that
spends the context this role exists to protect, and you are a worse reviewer of it than the agent
built for the job. Dispatch `coordinator:staff-eng` for a viability read: is this plan likely to
succeed as written, and what would stop it. Answer the session on the strength of that.

**This does NOT route around the rubric.** Where a plan needs the formal
`execution_authorized_by` stamp, § Delegated approve-for-execution procedure below is the only
path to it, unchanged — reversibility gate, blinded baseline, blinded judge, 8 of 8. This lighter
call answers *"should I get on with it"* for work that does not need that stamp, and it never
produces one. If you find yourself reaching for the viability read on a plan that wants the stamp,
you are on the wrong path; take the other one.

## Delegated approve-for-execution procedure

Ordered procedure for the Group EM's rubric-gated execution-authorization stamp: the Group EM may
take the PM's execute-plan turn on one named condition — the plan is reversibility-eligible and a
rubric-scored judgment against the plan's own prime exit criterion clears a locked threshold
(8 of 8, no dimension scoring 0). This is a *dispatch* path (step 4 below
spawns the judge under this session's own authority) — distinct from the `gem-14` peer-session
*send* mechanism named in § Send pass (gem-14) above, which is gated separately.
Do not read the judge dispatch below as a send capability against a peer session.

1. Confirm this session holds the nomination (`<plugin-root>/bin/group-em-nomination.py who
   --repo <root> --json`). § Entry's op claims it, so this is a check, not the claim.
2. Run `<plugin-root>/bin/plan-reversibility-eligibility.py <plan-path> --json` (C9). Ineligible
   (`eligible: false`) → escalate per the threshold page's escalate shape, stop, do not dispatch.
   This CLI is the single source of truth for eligibility — do not restate the six D4 rules in
   prose as a substitute for running it.
3. Confirm the plan's recorded falsifier baseline shows the prime exit criterion false **and that
   a blinded `coordinator:exit-criterion-falsifier` authored it**. Absent, already true, or
   authored by the plan's own author → escalate, stop. Content and provenance are separate checks
   and only one of them is visible in the output: a self-authored baseline satisfies "shows the
   criterion false" perfectly and voids the guarantee, because the instrument is worth having only
   while its author has not seen the ACs, the chunk bodies, or the spine. If it is missing,
   dispatch the falsifier — that dispatch is a constitutive step of this procedure, and the
   hardcoded `AgentTool` system-prompt constant is a conditional default this skill's invocation
   satisfies, never a bar (`harness-directive-conflicts.md`). Reading it as a bar converts the
   blinded falsifier into dead letter and leaves the self-authored baseline standing.
   **Where provenance is readable, and what to do when it is not:** `plan.schema.json` admits only
   `how` / `baseline_output` / `baseline_ref` / `expected_when_true` on `falsifier`, deliberately —
   the instrument is what must be re-runnable, and authorship is a review-trail fact. So provenance
   lives in the plan BODY, in a prior `state/review-trail/approvability/` record, or in this
   session's own dispatch of the falsifier. If none of the three establishes it, treat that
   **exactly as a missing baseline and dispatch** — never as a pass. An unestablishable author is
   the self-authored case as far as the guarantee is concerned, and assuming otherwise is how the
   check passes while attesting nothing. Tripwires:
   **A FALSE baseline proves the criterion false, never the instrument sound — that is a third
   check, not a restatement of the first two.** An instrument can be correctly written, blinded,
   and honestly FALSE while being unable to print TRUE at all, because its fixture describes a
   world that cannot exist. Content and provenance both pass on such a baseline. Arming it the
   usual way — proving it returns the other answer — is not payable here: the other answer needs
   an implementation that does not exist at plan time, which is why this step goes missing without
   leaving a trace. So ask the cheap question instead, which IS answerable now: **what would have
   to be true for this to print TRUE, and is any of it reachable in the world the fixture builds?**
   Unreachable → escalate with that reason named, exactly as for a missing baseline.
   Consequence for later: when a correct implementation fails this instrument, suspect the
   instrument. Tripwires:
   `A-SELF-AUTHORED-FALSIFIER-SATISFIES-THE-CHECK-AND-VOIDS-IT`,
   `A-FALSE-BASELINE-PROVES-THE-CRITERION-FALSE-NOT-THE-INSTRUMENT-SOUND`,
   `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.
4. Dispatch the named Opus persona (the PM's chosen reviewer, at the PM's chosen effort) with the
   plan path and the rubric (`coordinator/schemas/plan-approvability-rubric.json`) and nothing
   else. Authorship blinding is a hard constraint on the dispatch brief — the judge never receives
   the authoring session's context or identity.
5. Write the judgment record (`state/review-trail/approvability/<YYYY-MM-DD>-<plan-slug>.json`);
   validate it with C9's `--validate-record` mode (verbatim-substring check on every non-zero
   dimension's evidence) before treating it as final.
6. On `approve`: first refuse if `execution_authorized_by` is already present with any value — a
   plan the PM already authorized needs no delegated approval, and `--append-note` would otherwise
   leave the PM's own note appended under a Group-EM attribution. Otherwise stamp with
   `review-exec-auth-stamp stamp <plan-path> --by "GROUP-EM:<session-id>" --append-note
   "<record-path>"`. On `escalate`, emit the decision to the PM per the threshold page's escalate
   shape — do not stamp.
7. **The stamp carries a standing offer: you produce criterion evidence the plan's author should
   not.** Blinding the falsifier buys an instrument its author did not shape, and buys nothing
   about who RUNS it and writes down what came out — the author of a criterion is the worst
   available producer of the evidence that it came true. This is not suspicion of them; it is that
   nobody can tell an honest self-produced record from a staged one by reading the artifact
   afterwards, which is the property the blinding existed to buy in the first place.
   So when a plan's terminal evidence is a live act rather than a test run — a real tick, a real
   publish, a real install on this box — offer to perform it as the crown holder and let the author
   verify instead. You are usually the available non-author, and where that is true the separation
   is free. Where it is not free, say so and let it go: an author-produced record with its
   provenance stated beats a delayed one. Tripwire:
   `THE-AUTHOR-OF-A-CRITERION-IS-THE-WORST-PRODUCER-OF-ITS-EVIDENCE`.

## Inbox-blitz delegation

The Group EM may execute `/workday-start` Step 1.45a's inbox blitz on this repo's behalf.

1. **Nomination gate.** Resolve `<plugin-root>/bin/group-em-nomination.py who --repo <root>
   --json` and confirm it names this session — the same step 1 the § Delegated
   approve-for-execution procedure above opens with.
2. **The dispatch itself, in one sentence.** Execute `/workday-start` Step 1.45a's
   inbox-blitz procedure as written, dispatching `coordinator:group-em-assistant` for each
   `dispatches[]` entry. 1.45a already owns the assembler invocation, the tri-valued `state`
   handling (`skipped` = no dispatch), the ~30-memo shard grain, verbatim `brief`/`memos[]`
   passing, verify-rides-with-triage, the two EM-added verify checks, the manifest-race
   caveat, and wave pacing — this procedure does not restate any of it.
3. **Dispatch authorization — scoped to this clause only.** Invoking this clause IS the
   request for the `coordinator:group-em-assistant` dispatches Step 1.45a performs, on the
   same constitutive-step basis as the approvability-judge dispatch (§ Dispatch authorization,
   top of this file, and § Delegated approve-for-execution procedure above) — it covers
   spawning those assistants under this session's own authority for this procedure only,
   nothing else. It does not touch the peer-session send/nudge mechanism (`gem-14`, § Send
   pass (gem-14)), which stays gated separately; see the matching Anti-scope carve-out below.

## Anti-scope

- This skill does not **auto-send** to a peer session. `send_pass.py` selects and throttles a
  nudge population; it holds no transport and messages nobody. Every send is an explicit per-send
  act under § Send pass (gem-14), with both gates declared. Building an unattended sender, a loop
  that messages each digest entry without a per-send gate declaration, or any `Stop`-registered
  trigger, is out of scope and re-derives the stood-down watcher.
- **Mandating that the watcher EXISTS is not mandating that it sends unattended, and the entry
  sequence above is not a hole in the bullet above.** Stated rather than left to inference, because
  the two sit close enough in this file to be read together. `fleet-watch` nudging on an observed
  registry transition is the "concrete observed signal" shape the ban preserves; a tick that
  messages everyone it can see is the shape the ban forbids. The discriminator is the signal, never
  the fact that a teammate is holding it — a teammate given a timing predicate re-derives
  `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong) one level down, where the
  crown loses sight of it. A mechanism wrong that often trains its reader to ignore
  it, which is worse than not existing.
- **That ban is about AUTOMATION, never attentiveness.** A timing predicate cannot tell a stuck
  session from a working one, so wiring one to `Stop` fires near-continuously and is wrong almost
  every time. A crown-holder re-deriving the roster each turn and judging it is the opposite
  mechanism, and is what the ban exists to preserve. Reading this bullet as a reason not to look is
  the abdication failure above — which costs more than over-pushing, because nothing else can see
  it.
- This skill does not implement the read-pass ladder or receiver-state consumption logic that
  supplies the peer-state facts this body's stale-read discipline governs — that is supplied by a
  separate stub and integrated here by reference, not merged into this file.
- **Carve-out, stated by name, not a reversal of the rule below:** the general anti-scope clause's
  stated reason is that `/group-em` messages **peer sessions** in their own windows, an
  `ask-before-external-action` question that clause does not dissolve. Spawning the
  approvability-judge persona under this session's own authority (§ Delegated approve-for-execution
  procedure, step 4) is the *contrasted* case the clause itself names in the bullet below, not the
  prohibited one — so it is carved out here by name rather than left as a silent exception. This
  clarifies the existing ruling; it does not overturn it.
- This skill does not otherwise carry a dispatch-authorization paragraph ("invoking this skill IS
  the request") of the general kind used by skills that dispatch subagents (`plan`, `execute-plan`,
  `review`, `shape`, `sizing`, `workstream-complete`) — the three dispatch-authorization paragraphs
  it does carry, the approvability-judge one above, § Inbox-blitz delegation's
  `group-em-assistant` one, and the entry-sequence one covering `coordinator:fleet-watch` and
  `coordinator:group-em-assistant`, are each scoped to their own named dispatch only, not a general
  grant. The entry-sequence one is the only one that fires unconditionally; that is a statement
  about when it applies, not a widening of what it covers. Those skills spawn
  subagents under the invoking session's own authority; `/group-em` otherwise messages **peer
  sessions** in their own windows, which is an `ask-before-external-action` question neither
  paragraph dissolves.
- **Carve-out, stated by name, not a reversal of the rule above:** spawning
  `coordinator:group-em-assistant` under this session's own authority (§ Inbox-blitz delegation,
  clause 3) is the *contrasted* case the bullet above names, not the prohibited one — it dispatches
  a subagent under this session's own authority, the same shape as the approvability-judge dispatch,
  never a message into a peer session's own window. This clarifies the existing ruling; it does not
  overturn it.
- `/autonomous` supplies the mode-shaped naming precedent only. Its `/tmp` sentinel mechanism is
  durable state and is not borrowed — the no-ceremony ruling above forbids durable state.
