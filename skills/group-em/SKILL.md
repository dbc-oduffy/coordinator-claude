---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo, never plan or author on their behalf."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "CronCreate", "CronList", "CronDelete", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke to start monitoring this repo's peer sessions]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

`/group-em` switches this session into monitoring the other sessions in the same repo and moving
them along. A **mode a session enters, not an operation on a target**.

**THIS BODY IS A SNAPSHOT, FROZEN WHEN YOU ENTERED, CARRYING NO VERSION.** It renders identically
to the live file however old it is, and nothing signals drift. **Before citing it as authority for
anything MECHANICAL — a signature, a module path, a flag, a refusal vocabulary — read that passage
from disk.** One read, and it removes a class of confident wrongness you cannot otherwise detect:
this skill's own step 4 changed today, and a crown acting on the pre-change snapshot hit an
`AttributeError` and reported it as an engine defect. The earlier a session entered, the more
confidently stale it is. Prose and disposition here age gracefully; call shapes do not.

**PM-GATED — only on an explicit PM ask, never EM-initiated.** A description-prefix convention
(as `staff-session`, `spinoff`, `roadmap-planning`); no hook enforces it. Honoured by disposition.

**Dispatch authorization — invoking this skill IS the request, for two specific dispatches only:**
the approvability judge (§ Delegated approve-for-execution, step 4) and
`coordinator:group-em-assistant` at entry, and § Inbox-blitz delegation's assistants. Each covers
raising that named role under this session's own authority and nothing else, by unnamed
`Agent`-tool dispatch. **None of them touches the peer-session send mechanism (§ Send pass,
`gem-14`), which stays gated per send. Navi is not covered by this grant — it is PM-gated per the
line above, raised only on an explicit PM ask, never under this session's own authority.**
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

**INTRODUCE YOURSELF TO EVERY LIVE PEER, ONCE, AT ENTRY.** The second owed send, same class as the
displaced holder's and likewise exempt from § Send pass's gates. A peer that does not know who holds
the crown routes its asks to the PM instead — the standing failure this mode exists to absorb — and
nothing in the entry payload tells them. The roster is the population; skip only a `PAUSED:away`
peer, and resolve each addressee immediately before sending (§ Send pass step 4) since a name
re-points with no event.

Say four things and stop: **who you are** (name and session id), **that you hold the Group EM
standing for this repo**, **what to route to you** — a blocked dependency, a collision with another
session on one file, an escalation they were about to send blind — and **that no reply is wanted**.
Close with the last one explicitly; without it a peer spends a turn acknowledging, and five
acknowledgements is the interruption the gates exist to prevent.

**Do not ask peers to route their PM reports through you.** § The escalation screen is about a
session escalating BLIND — one that has no PM channel open and would otherwise hand the PM a next
step it already owns. A session the PM is actually typing into has a direct channel, and relaying
its report through you adds a hop and puts its words in your mouth. Offer the screen for
*"should this go up at all"*; never insert yourself into a conversation that already exists.
A peer that pushes back on this is right, and it is a correction the introduction's own wording
invites if it says "anything for the PM" rather than "anything you were about to send blind".

**It is an introduction, not a nudge, and the difference is enforced by content.** It asks nothing.
No *"what are you working on"*, no *"anything blocking you"*, no status request, no question mark
anywhere. Those are nudges, they need both gates per peer, and smuggling one into a broadcast that
skips the gates is the failure this paragraph exists to prevent. If a peer's state genuinely needs a
nudge, that is a separate send, gated normally, later.

**It arms no cooldown and is not an offer.** Only `build_send_digest` emitting an entry arms a
peer's throttle, so introducing costs nothing against the first real offer — do not route it through
the digest to make it look like one.

**Once per PEER, not once per tick and not only at entry.** Entry introduces the peers live then;
a peer appearing in a later roster read is introduced when it appears. That is the same
once-per-peer rule, not a re-broadcast — the tick never re-sends to a peer already introduced, and
the loop stays bounded to peers not yet introduced.

**Track who you introduced by SESSION ID, never by name.** A name re-points with no event, so a new
session inheriting a departed peer's name reads as already-introduced and silently never learns who
holds the crown — the failure the introduction exists to prevent, reappearing through the roster's
own bookkeeping. Measured: `doe-claude-95` went `GONE` and a different session held that exact name
inside twenty minutes, with `resolve_addressee` refusing the old pairing
(`name-now-points-at-a-different-session`) and accepting the new. Introducing at entry only, or
keying the introduced-set on names, both leave that session uncovered.

## What this skill does and does not do

**Does NOT plan or author on anyone's behalf** — never plan bodies, stub content, or roadmap
decisions for the sessions it watches. **DOES coordinate execution waves and cross-session
sequencing** — a stalled wave, a peer blocked on a dependency that has cleared, two sessions about
to collide on one file.

## Entry dispatches both standing watchers; Navi is PM-gated

**ENTRY DISPATCHES BOTH STANDING WATCHERS — `group-em-assistant` AND THE WATCH IT ARMS ARE
MANDATORY.** Navi is PM-GATED — only on an explicit PM ask, never EM-initiated (same convention as
the top of this file) — entry never raises it under this session's own authority.
**DISPATCH `group-em-assistant` WITHOUT A `name`.** `group-em-assistant` is per-repo and is the
one that gets asked things, so it keeps today's shape: a named `Agent` call spawns an in-process
TEAMMATE, and a teammate is never re-invoked by a `Monitor` it armed — so a named watcher cannot
hold its own wire and you inherit a relay. Unnamed, it is a background agent that wakes on its own
events (`docs/research/spike-verdicts/2026-09-02-subagent-self-armed-wake.md`). Address it by the
`agentId` its dispatch returns.
**"Entry" here means you, on entering the mode — not the entry op.** `group-em-enter.py` assembles
and dispatches nobody. The autofire hook is silent either way, so its silence is not a report that
these were done. Entry assembles once; nothing re-runs it, and a roster read is stale within a
minute. In this order, as your first act:

1. **`coordinator:group-em-assistant`** — dispatch it, unnamed. Your standing reader AND your
   per-repo sensor: transcript tails, baton claimants, what landed on a path since a SHA, **and the
   watch SUBPROCESS together with the `Monitor` over it**. Warm across the session, woken by its
   own `Monitor` over `cross-repo/inbox/`, by the watch subprocess's stdout, and by `SendMessage`
   between times. It owns the sensor half in full: arming the watch, the `Monitor` that wakes it
   off that watch, park-spool triage, and holding `state/group-em-watch.json`.

   **Arm the watch as one of its first acts, via the settings-home trampoline**, which resolves the
   engine for it and therefore works from any repo:

       $COORDINATOR_SETTINGS_HOME/bin/group-em-watch --repo-root <root> --group-em-session-id <your sid>

   `persistent: true`. **`--group-em-session-id` is passed explicitly, never defaulted** — it is a
   separate id from `--caller-session-id` (the caller is whatever process polls; the Group EM is
   whose offer log suppresses an already-answered peer), and they diverge the moment the assistant
   holds the watch. It emits one line per peer entering a parked state, derives parked from
   `read_pass.classify_peer` rather than a registry `status` field, stays silent while that peer's
   cooldown is armed, and never disarms. Two other modes: `--status` answers "is a watch alive
   here?" in plain words and exits (0 alive, 1 not running, 2 unknown — **unknown is never
   green**); `--once` fires a single tick, the form a cron floor uses.

   **Prefer the trampoline to the bare module.** `python -m coordinator_core.group_em.watch` needs
   the engine already importable, so it starts only from an engine-rooted cwd; from a doctrine repo
   it is a `ModuleNotFoundError` at start-up, and a watcher whose subprocess never started presents
   as `idle` — indistinguishable from a quiet fleet, no error anywhere. Reach for the bare module
   only if the trampoline is genuinely absent from this box, and confirm the subprocess started
   rather than trusting its silence.

   **Arming can REFUSE, and a refusal is not a quiet result.** `WatchAlreadyHeldError` — *"a watch
   is already armed for this repo"* — means the sensor never started. Do not read it as
   "already covered": verify with `--status` that the holder is a real watch and not a stale
   record, and never leave the turn on an unverified refusal.

   **`--status` saying ALIVE is not that verification, and the tell is two lines down.** Read for
   *"Reported on nobody: 0 subscribed peers"* — that is the holder that armed nothing. Its
   ABSENCE is currently not evidence of a real watch: the guard emitting it is disarmed whenever
   the record carries declination rows, which entry always writes, so an entry-only stamp renders
   with the reassurance line instead. Until that is fixed, an ALIVE with no population line is
   unresolved, not confirmed — read `state/group-em-watch.json` and treat `tick_source: entry`
   with `subscribed_peers: 0` as a holder that never armed. Standing down on `--status` alone
   leaves the fleet unwatched by exactly the procedure meant to prevent it.
2. **A `CronCreate` tick**, ~23 minutes, off the :00/:30 marks — the only clock that stays yours.
   It audits the watch rather than performing it: *is nudging happening, what is the state of the
   batons and live plans, is anything stuck nobody has poked.*

   **That prompt is a DOCTRINE SNAPSHOT that re-executes on a timer, and it is the one artifact a
   doctrine fix cannot reach.** A skill body is re-read at every invoke, so correcting this file
   reaches the next `/group-em` — which is exactly what makes the gap invisible: the fix genuinely
   works, while every running holder's tick keeps firing the text it was authored with. Nothing
   shows it. `CronList` looks healthy, the job fires on schedule, and the instruction inside is
   stale. Measured today: a Group EM's tick carried a comparison this file had since corrected away,
   and would have re-derived the same false positive every 23 minutes indefinitely.
   Two mitigations, both cheap. **Open the tick with "re-enter `/group-em` first, and if anything
   here contradicts the skill, the skill wins"** — that makes the snapshot self-correcting for
   anything the skill covers. And **re-author the job when this skill changes under you**: delete
   and re-create it, naming the SHAs, so the superseded text is not reconstructable by a later holder.
   The frozen artifact everyone watches for is a stale summary; this one is a stale *instruction*,
   and unlike a summary it acts.

**Not numbered, PM-gated: Navi.** When the PM asks, **spawn it, never an `Agent`-tool dispatch.**
Its mood is SPAWN; a Navi raised as a subagent is the wrong role in the wrong shape, and its own
role file refuses it.

    claude --agent navi --bg

The machine-wide nudge role: repo-less, decision-weightless, holds no repo of its own, and never
nudges a stalled peer twice. It nudges on your behalf and refers every question back to your own
Group EM standing. **It escalates TO you; it cannot be asked anything** — a separately spawned
session is measured UNREACHABLE inbound, so there is no ask path to reach for, only its own
escalations to read (`state/audits/2026-09-02-session-shaped-watcher-mechanics.md` leg (4)). If the
PM asks for it, keep its session id for the record.

**Raise the mandatory pair yourself, from this session.** A watcher belongs to whoever raised it,
so one raised by another session relieves that session and leaves you watching while believing you
were relieved.

**THE `Monitor` GOES TO `group-em-assistant`, AND IT IS THEIRS TO ARM.** They own the subprocess
and the wire out of it: `persistent: true`, filtering
`PARKED|ESCALATE|OUT-OF-WORK|GROUP-EM-MOVED|UNKNOWN` plus failure signatures. **This works only
because they are dispatched unnamed.** Dispatch them with a name and the same arm produces a
healthy sensor writing park events that reach nobody — every event you see then arrives because
you asked on a tick, never because anything pushed, and the arrangement looks correct from every
surface: watcher alive, subprocess alive, log filling. Measured: ~50 minutes of exactly that, and
0 wakes out of 3 on demand. Tripwire:
`A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`.

The wire also needs a liveness arm, because a sensor that dies silently is indistinguishable from a
quiet fleet — but **do not shape that arm as a process-table check.** `pgrep -f` cannot read Windows
process command lines, and even where it can, the watch runs under two different command lines
(`python -m coordinator_core.group_em.watch`, or the trampoline's `group-em-watch.py`), so a pattern
matched against either one reports a false death for the other. A false death is worse than no arm:
it teaches the holder to discount the one wire that wakes them. Measured twice in one afternoon on
two boxes — once from `pgrep -f` on Windows, once from a watcher grepping the module path while the
trampoline was running.

**Carry liveness on `last_tick_at` age in `state/group-em-watch.json` instead** — already the
sanctioned instrument in § Liveness instruments, and portable. Compare it against the record's own
`next_expected_by` rather than a threshold you pick: the cadence is measured at arm time and varies
(~12 s for a `Monitor`, ~23 min for a cron tick), so a fixed number is trigger-happy or blind
depending on which instrument stamped last. The writer is the only party that knew its own clock.

**The `notify_when_idle` one-shot is the one thing that CANNOT be delegated** — the harness accepts
it only from a main conversation, in either dispatch shape. **This still binds:** `group-em-assistant`
is still a subagent, not a spawned session, so nothing about this rewrite changes who it can be
accepted from — it stays with you if it is used, and the poller is the better clock regardless. (Navi
is a spawned session and could in principle hold a main-conversation one-shot, but it holds no repo
to notify against, so this stays moot for it.) Do not confuse it with the `Monitor`: they used to
share one rule and one reason, and only this half of it was ever true.

**You no longer relay events.** `group-em-assistant` hears its own wire and acts on it; your move
on a park is nothing. What still reaches you is what they escalate — an `OUT-OF-WORK` peer needing
work, a `GROUP-EM-MOVED`, anything needing a decision. **The tell that you have taken the relay
back: you find yourself waking them, or working an event they already hold.** Both mean you are
paying for a standing assistant and doing its job. Navi's escalations reach you the same way, but
in one direction only — you cannot wake Navi to ask it anything, only read what it sends.

**The park spool is `group-em-assistant`'s surface to read and triage, not yours to tail** — see
"The wake has a producer" below for the mechanism. Ask `group-em-assistant` for it rather than
going to the file first: one record per turn end per session, on a box running ~20 concurrent
sessions, is exactly the triage work a standing assistant exists to absorb — piping it into your
own context is the work you delegated, undone. The spool does not add a third thing to arm — the
`Monitor` over the poller's stdout is theirs and already covers the wake. **They triage and
report; they never nudge a peer** — nudging is Navi's alone, or the Group EM's own.

What the two clocks buy you, so "how fast would you know?" has an answer: the held poller's cadence
is measured once at arm time, floored 5 s and ceilinged 300 s, and `ARMED` prints the resolved
number — read your own rate off it rather than assuming one; the ~23-minute cron tick is the floor,
and the only clock still running when nobody holds a watch at all.

**Verify each clock's holder, never assume it.** `CronList` shows your tick; the `Monitor` and the
subprocess are `group-em-assistant`'s, and their report of them is your instrument — ask, do not go
and look. A watcher that armed nothing renders identically to one holding a live wire, so the check
is that they NAME the monitor's task id and the poller's resolved cadence, not that they say
"armed".

**A Group EM holding neither teammate is what this sequence exists to prevent, and it is not
hypothetical.** Worked case:
`coordinator/docs/wiki/group-em-entry-teammates.md`.

**Before arming either party, read `holder_session_id` from `state/group-em-watch.json`.** A fresh holder
that is not you means someone is already watching; arming beside them is the half-handover and
nothing refuses it for you. But **a fresh holder may be a prober, not a watcher** — running the arm
command at all, `--max-iterations 2` included, stamps the record. Ask whether that session
plausibly watches this repo before standing down: a holder from another repo, or one carrying
`subscribed_peers: 1`, ran the command once. The record is untracked runtime state, ages out on its
own, and is never repaired by hand.

**Both clocks, deliberately: PM-ruled belt-and-suspenders.** A poll and an event watch fail
differently. Entry covers both — poller via `group-em-assistant`, cron yours — and never arms one
twice.

**That is a rule about entry, NOT a bar on re-arming a spent clock.** Prefer the clock that cannot
be spent. A one-shot (`notify_when_idle`) fires once per peer and leaves it unwatched, so a watch
armed only at entry decays to covering the peers that have not yet stopped — and an exhausted watch
and a quiet repo emit identically. Where a one-shot is used, re-arming it per peer per tick is
required, not duplication.

**Each tick records a DECLINATION for every roster entry it does not message** — which gate failed
and why. A tick closing on "nothing sent" with no declination is indistinguishable from one that
never looked.

**And each tick STAMPS them to disk**, via `watch_heartbeat.stamp(repo_root, holder_session_id,
declinations, interval_seconds, subscribed_peers=…, tick_source=…, writer_session_id=…)`. Copy that
order: `declinations` is the THIRD positional and `interval_seconds` the fourth and required, so a
call shaped `(repo_root, session_id, name, source, declinations)` raises rather than stamping — and
a tick that raises here is exactly the tick that cannot tell "looked, nothing to do" from "did not
look". `writer_session_id` is a keyword, **optional in the signature and required at runtime**: the
call raises on a falsy value, so an omitting call refuses once and succeeds only on the retry. It is
YOUR session id — the instrument doing the writing — which is not `holder_session_id` when a
delegate arm stamps on the crown's behalf; the two together are what let a reader tell one crown's
two instruments apart from two crowns racing.
`tick_source` is `cron` or `monitor` and is a KEYWORD, never positional; entry stamps its own.
`declinations` is THIS tick's rows only — each `{session_id, name, gate, reason}`, never an
accumulating history; a tick that declined nothing passes `[]`. `subscribed_peers` is the count your
`Monitor` arm is *still* subscribed to right now, not the count you armed. A declination held only
in your context dies with you.

**The engine must be importable, which it is not from the repo you are Group EM for.** `stamp`,
`idle_report` and the watch runnable all live in `coordinator_core`; invoked from a doctrine repo's
root they raise `ModuleNotFoundError` before doing anything. Run them from an engine-rooted cwd, or
via the settings-home trampoline — **`$COORDINATOR_SETTINGS_HOME/bin/group-em-watch`, which on a
default install is `~/.coordinator-claude-settings/bin/group-em-watch` (`.exe` on Windows).** Name
it that way when you brief a watcher: it is NOT under `~/.claude/bin`, `~/.claude/plugins/bin`, or
the engine's own `bin/`, and a holder who probes those three concludes the trampoline is absent and
briefs the bare-module fallback on a false premise. Measured on two boxes. **On
Windows, invoke it through the call operator with forward slashes** — `& "$env:COORDINATOR_SETTINGS_HOME/bin/group-em-watch.exe" --repo-root ... --group-em-session-id ...`; the
documented bare form is a PowerShell PARSER error, which fires before anything runs and reads
nothing like a bad argument. Measured: three restart attempts, the first two lost to this. It is
the same false premise arriving by a second route — a holder who gets a parser error twice, having
already read that the trampoline may be absent, concludes exactly that and falls back to the bare
module, which `ModuleNotFoundError`s, which presents as `idle`, which is indistinguishable from a
quiet fleet. A tick that assumes the
import worked reports a stamp it never wrote.

**The wake has a producer; you arm nothing for it.** `state/group-em-watch-spool.jsonl` gets one
record per park, appended by every session's own `Stop`
(`coordinator/hooks/scripts/group-em-park-spool.py`, registered in `stop-dispatch.py`) when its
park verdict lands. It is a hook, so it needs no entry step and no holder — but it only fires where
this plugin's hooks are installed. The engine plane commits to the spool retaining at least the last 30
minutes of parks, so a Group EM running `group-em-assistant` needs no separate drain step.

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
`group-em-assistant`'s normal state between polls, so a live watcher and a dead one render
identically on the only surface a human has. Answer from `last_tick_at` age and name the
instrument, so the PM has
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

**`roster` IS NOT THE POPULATION — it is the shortlist, and comparing it to the room raises a false
alarm on every busy repo.** It is `build_candidate_roster`'s output: `candidate ∪ unclassifiable ∪
contradicted`, which on a busy repo is a small fraction of what entry enumerated (measured
engine-side: 11 peers enumerated, 2 in `roster`). A human adjudicates it. The obligation ledger
ranks and annotates, never admits — `undischarged_obligations: None` means no ledger exists, a
producer coverage gap rather than evidence the peer owes nothing.

**The trap that has actually fired.** A digest of `0 entry(ies)` reads as a quiet fleet, and says
that identically whether every peer was weighed and held or none was ever enumerated. **Compare
`roster_considered` — the enumerated count entry reports top-level — against the room, never
`len(roster)`.** A `roster` smaller than `roster_considered` is NORMAL and means peers classified
out of the shortlist; a `roster_considered` smaller than the sessions you know are running is
`unknown`, never quiet, and those peers were never enumerated, so nothing in `suppressed` mentions
them.

Getting that numerator wrong is not theoretical: a Group EM comparing `len(roster)` to the room
found a peer "silently dropped", confirmed it live and present in two earlier rosters, and reported
a break-class defect — for a session whose classification had simply moved out of the union. The
comparison had looked sound on the two prior ticks because every peer happened to classify in, which
is the worse failure: **a check that is coincidentally right is harder to catch than one that is
plainly wrong.**

Two settling reads: `claude agents --json` counts the room without this ladder, and `python -m
coordinator_core.group_em.idle_report --repo-root <root> --group-em-session-id <your sid>` derives
the population independently. Only `--repo-root` is CLI-enforced (exits 2 bare on omission);
`--group-em-session-id` is required BY THIS PROCEDURE, not by the CLI — the parser defaults it to
`None` and accepts the omission silently, degrading offer-log suppression rather than erroring.
Pass it anyway; omitting it does not fail loud. Three instruments disagreeing on how many peers
exist is a defect to report, not a number to average.
<!-- Review: coordinator:code-reviewer, finding 2 — the CLI does not enforce this flag; fixed the
     claim to name the requirement as this procedure's own and state the silent-degradation
     consequence. -->

**And a healthy-looking count does not clear this line, because one symptom has two producers.**
`Roster: 0 peer(s), 0 candidate(s)` was emitted both by a missing `build_roster` export and by the
entry hook rendering the shortlist as the population — byte-identical output, independently
sufficient. Both are fixed (`a670047c4f` engine-side, `c85f9fdf4` here), and the point survives the
fixes: when a passing check has more than one possible producer, it argues for none of them
(`A-GATE-THAT-CANNOT-GO-RED-IS-NOT-COVERAGE`).

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
4. **Re-resolve the address from the SESSION ID immediately before sending, and treat a refusal as
   a refusal.** `send_pass.resolve_addressee(repo_root, peer_session_id)` re-enumerates live and
   returns the name that session answers to right now, or `None`. **`None` means do not send.**

   **Resolve from the id, never validate the name — the id is the stable identity and the name is
   the volatile address.** A peer name re-points with no event and no visible difference at the call
   site, so the name you read off the roster may by now mean a different session. Going id → name
   hands you that session's CURRENT address and the send still lands where you meant; validating
   the stale name instead only tells you it went bad, and refuses a send that re-addressing would
   have delivered. You always hold the id: every roster row carries it, and so does
   `displaced_holder`. Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

   **`None` covers four cases: the session was absent from the roster, its row carried no name, the
   roster read failed, or the name is ambiguous** — two live sessions answering to it refuses rather
   than resolves, since `SendMessage` addresses by name and an ambiguous address lands wrong as
   easily as a stale one. Verified behaviourally against the published mirror, not inferred from a
   commit.

   **It does NOT filter by repo, and never has in either plane** — a name resolving outside this
   repo comes back as a clean address. That is the one gap to carry yourself.

   Note the direction if you are reading older prose or an older skill snapshot: this step once
   specified a name-first `read_pass.resolve_addressee(name, expected_session_id, repo_root=...)`.
   **That function is real** — the plugin-local ladder implements it, typed refusals and all, and it
   resolves correctly against the live registry. It was replaced on the direction argument above,
   not for being missing. What IS missing is any engine-side equivalent: `coordinator_core`'s
   `read_pass` has no `resolve_addressee`, and `send_pass.resolve_addressee(repo_root,
   peer_session_id)` is the id-first one. So the same call means two different things depending on
   which plane answered — the trap in `TWO-MODULES-ONE-RECORD-ARE-TWO-SIGNATURES`, and the reason
   this step now names the module as well as the function.

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
- **Mandating that the watcher EXISTS is not mandating that it sends unattended.** Navi nudging on
  an observed registry transition is the "concrete observed signal" shape the ban preserves; a tick
  that messages everyone it can see is the shape it forbids. The discriminator is the signal, never
  that a session holds it — a session given a timing predicate re-derives
  `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong) one level down, where you
  lose sight of it.
- **That ban is about AUTOMATION, never attentiveness.** A timing predicate cannot tell a stuck
  session from a working one. A holder re-deriving the roster each turn and judging it is the
  opposite mechanism and is what the ban preserves. Reading this as a reason not to look is the
  abdication failure above, which costs more than over-pushing because nothing else can see it.
- This skill does not implement the read-pass ladder or receiver-state consumption logic — supplied
  separately and integrated by reference.
- **The two dispatch grants at the top of this file are each scoped to their own named dispatch.**
  Raising the approvability judge and `group-em-assistant` under this session's own authority is the
  grant — both under the same shape as `plan`/`execute-plan`/`review` spawning subagents. What stays
  gated is that `/group-em` otherwise messages **peer sessions in their own windows** — an
  `ask-before-external-action` question no dispatch grant dissolves. The entry-sequence grant is the
  only one that fires unconditionally; that is when it applies, not what it covers.
- `/autonomous` supplies the mode-shaped naming precedent only. Its `/tmp` sentinel is durable state
  and is not borrowed.
