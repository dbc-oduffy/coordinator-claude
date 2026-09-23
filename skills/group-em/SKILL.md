---
name: group-em
description: "PM-GATED. Monitor peer sessions in this repo, never plan or author on their behalf."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "SendMessage", "CronCreate", "CronList", "CronDelete", "Monitor", "TaskStop"]
argument-hint: "[no arguments — invoke to start monitoring this repo's peer sessions]"
---

# Group EM — Peer-Session Monitoring and Wave Coordination

`/group-em` switches this session into monitoring the other sessions in the same repo and moving
them along. A **mode a session enters, not an operation on a target**.

**THIS BODY IS A SNAPSHOT, FROZEN WHEN YOU ENTERED, CARRYING NO VERSION.** Before citing it as
authority for anything MECHANICAL — a signature, a module path, a flag, a refusal vocabulary —
read that passage from disk. Worked case: `coordinator/docs/wiki/group-em-standing.md` § A
snapshot body is confidently stale.

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
perform. **If that context is absent, entry did not happen** — the hook fails open, so its silence
is a fact, never a reason to assume success. Run `<plugin-root>/bin/group-em-enter.py --repo <root>
--session-id <your sid>` and find out why. **`--session-id` is not optional** — it defaults to
`$CLAUDE_SESSION_ID`, unset in many shells; without it the op refuses (exit 2). (Every
`<plugin-root>/bin/` CLI here is plugin-local with no settings-home launcher — resolve per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`, never cwd-relative.)

The op shims the engine's `groupem.enter` in-process — one call claims the nomination, then builds
the candidate roster, send digest, peer-set baseline, teammate-presence assertion and watch-liveness
read. **Exit 5 means a refused standing** — a live or unaccounted-for incumbent holds the role;
`roster`/`digest`/`baseline`/`teammates` are absent from the payload, not empty. **Exit 2 means no
resolvable session id.** Payload shape: `coordinator_core/ops/group_em_enter.py`'s module docstring.

Do not import `read_pass` / `send_pass` directly. They are the op's collaborators.

**Standing first, last writer wins.** Whoever invokes most recently holds the role; entry never
refuses over an incumbent and there is no override flag. Re-entry by the holder is a refresh.

### Two owed sends, both exempt from § Send pass's gates

**A displaced holder that is still running is OWED a message this turn.** `displaced_holder` and
`displaced_holder_live` arrive in the entry context; live means that session still believes it
holds the role. Not live means nobody to tell.

**The owed message also tells the displaced session that its watch is no longer the crown's and
must be stopped:** TaskStop the Monitor, then confirm the subprocess is gone, because the
trampoline's `python.exe` child is observed to outlive TaskStop. It must not re-arm under the lost
role. A displaced watch that keeps running goes quiet for the entrant's ~23-minute entry lease and
then retakes the record, after which the new crown's arm is refused.

**INTRODUCE YOURSELF TO EVERY LIVE PEER, ONCE.** The roster is the population; skip only a
`PAUSED:away` peer, and re-resolve each addressee immediately before sending (§ Send pass step 4).
Full rationale for all five constraints below: `coordinator/docs/wiki/group-em-standing.md` §
Owed introductions.

1. **Say four things and stop:** who you are (name and session id); that you hold the Group EM
   standing for this repo; what to route to you; and **that no reply is wanted**, stated
   explicitly.
2. **Never ask peers to route their PM reports through you.** "The PM is typing into that session"
   is unobservable from here — every session reads itself as the attended one. Key it instead to
   something CHECKABLE: **a session answering a question just asked in this exchange** has a
   direct channel; relaying its report adds a hop and puts its words in your mouth.
3. **It is an introduction, not a nudge, and the difference is enforced by content: it asks
   nothing.** No question mark anywhere.
4. **It arms no cooldown and is not an offer.** Only `build_send_digest` emitting an entry arms a
   peer's throttle.
5. **Once per PEER, not once per tick**, and **tracked by SESSION ID, never by name** (§ Send pass
   step 4). Measured case: `coordinator/docs/wiki/group-em-standing.md` § A name is not an
   identity. **Neither key is independently reliable**: a session id has been observed to change
   under a stable name, so a name match alone cannot confirm "already introduced" and a session id
   match alone cannot confirm "same peer as before." On ambiguity between the two, re-introduce —
   a redundant introduction costs nothing the once-per-peer rule protects against; a skipped one
   leaves a peer that never got the four things in step 1.

   **The introduced set is durable, not session-memory.** It has no store of its own — recording an
   introduction is a `send_pass.build_send_digest`-shaped append to the EXISTING send log
   (`state/subagent-share/<this-session-id>/group-em-send-log.jsonl`, § No registration ceremony,
   no persistence) as a **cooldown-ignored row type**: it participates in "was this peer already
   introduced," never in `_cooldown_remaining`'s throttle window. No new datastore. The writer is
   `coordinator/skills/group-em/send_pass.py` — DoE-owned (same plane as this skill, not the
   engine) — so this is a local contract on that file, not a cross-repo relay.

## What this skill does and does not do

**Does NOT plan or author on anyone's behalf** — never plan bodies, stub content, or roadmap
decisions for the sessions it watches. **DOES coordinate execution waves and cross-session
sequencing** — a stalled wave, a peer blocked on a dependency that has cleared, two sessions about
to collide on one file.

## Entry dispatches both standing watchers; Navi is PM-gated

**ENTRY DISPATCHES BOTH STANDING WATCHERS — `group-em-assistant` AND THE WATCH IT ARMS ARE
MANDATORY.** Navi is PM-GATED — only on an explicit PM ask, never EM-initiated (same convention as
the top of this file) — entry never raises it under this session's own authority. **Raise the
mandatory pair yourself, from this session**: a watcher belongs to whoever raised it, so one raised
by another session relieves that session and leaves you watching while believing you were relieved.

**"Entry" here means you, on entering the mode — not the entry op.** `group-em-enter.py` assembles
and dispatches nobody, and the autofire hook is silent either way. Entry assembles once; nothing
re-runs it, and a roster read is stale within a minute. In this order, as your first act:

1. **`coordinator:group-em-assistant`** — dispatch it, unnamed. Your standing reader AND your
   per-repo sensor: transcript tails, baton claimants, what landed on a path since a SHA, **and the
   watch SUBPROCESS together with the `Monitor` over it**. It owns the sensor half in full: arming
   the watch, the `Monitor` that wakes it off that watch, park-spool triage, and holding
   `state/group-em-watch.json`. Full remit: `coordinator/docs/wiki/group-em-assistant-remit.md`.

   **DISPATCH `group-em-assistant` WITHOUT A `name`.** A named `Agent` call spawns an in-process
   teammate, and a teammate is never re-invoked by a `Monitor` it armed — so a named watcher cannot
   hold its own wire and you inherit a relay. Unnamed, it is a background agent that wakes on its
   own events. Tripwire: `A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`.

   **Arm the watch as one of its first acts, via the settings-home trampoline**:

       $COORDINATOR_SETTINGS_HOME/bin/group-em-watch --repo-root <root> --group-em-session-id <your sid>

   `persistent: true`: DETACH it. A watch armed inside a subagent's Bash dies with the task while
   `--status` still reads ALIVE. **`--group-em-session-id` is passed explicitly, never defaulted** — a
   separate id from `--caller-session-id`. It emits one line per peer entering a parked state,
   derives parked from `read_pass.classify_peer`, stays silent while that peer's cooldown is
   armed. **It carries a documented re-arm duty, not "never disarms"** — a subprocess is observed
   dying ~60 minutes after arming, so the ~23-minute cron tick reads `last_tick_at` age (a
   sanctioned instrument, § Liveness instruments) and re-arms when the record is stale. On a
   re-arm refusal, read the record: if it names this session or its delegate, wait until its
   `next_expected_by` passes and retry once. Never hand-edit the record. No lifetime number is
   asserted here, because the cause is engine-owned. `--status` answers "is a watch alive here?" (0 alive, 1 not running, 2
   unknown — unknown is never green); `--once` fires a single tick.

2. **A `CronCreate` tick**, ~23 minutes, off the :00/:30 marks. It audits the watch rather than
   performing it. **Open the tick with "re-enter `/group-em` first, and if anything here
   contradicts the skill, the skill wins."** And re-author the job when this skill changes under
   you: delete and re-create it, naming the SHAs.

**Not numbered, PM-gated: Navi.** When the PM asks, **spawn it, never an `Agent`-tool dispatch.**
Its mood is SPAWN.

    claude --agent navi --bg

Repo-less, decision-weightless, never nudges a stalled peer twice. **One-per-box is held by
`navi-singleton.py`** (`TWO-NAVIS-ON-ONE-BOX-IS-A-SILENT-DOUBLE-NUDGE`). **It escalates TO you; it
cannot be asked anything.** Keep its session id for the record.

### Arming the watch — every refusal and every false green

**Before arming either party, read `holder_session_id` from `state/group-em-watch.json`.**

| Rule | The tell |
|---|---|
| Prefer the trampoline; confirm the subprocess started rather than trusting its silence. | The bare module needs an engine-rooted cwd; a watcher whose subprocess never started presents as `idle`. |
| **Arming can REFUSE, and a refusal is not a quiet result.** On `WatchAlreadyHeldError` verify with `--status`. A refusal naming the session you displaced is that retaking watch — tell it to stop. Do not wait it out, because it restamps every poll. Arm within the entry lease: an entry that never arms is a crown with no watch, and the displaced watch fills the gap. | *"a watch is already armed"* leaves the fleet unwatched if read as "already covered." |
| **`--status` saying ALIVE is not verification** — check `subscribed_peers`. | An ALIVE holder that armed nothing renders identically to a real watch. |
| **Read `holder_session_id` from `state/group-em-watch.json`** before arming beside a fresh holder. | A holder from another repo ran the command once; the record ages out on its own. |
| **The engine must be importable**, which it is not from the repo you are Group EM for — use `$COORDINATOR_SETTINGS_HOME/bin/group-em-watch` (`.exe` on Windows; on PowerShell, `&` + forward slashes). | A bare-module run from a doctrine repo raises `ModuleNotFoundError` before doing anything. |

Full mechanics and both false premises measured: `coordinator/docs/wiki/group-em-assistant-remit.md`
§ Arming the watch.

### The wires — who arms what, and how fast you would know

**THE `Monitor` GOES TO `group-em-assistant`, AND IT IS THEIRS TO ARM** — the subprocess and the
wire out of it, filtering `PARKED|ESCALATE|OUT-OF-WORK|GROUP-EM-MOVED|UNKNOWN` plus failure
signatures. **This works only because they are dispatched unnamed.** Tripwire:
`A-MONITOR-ARMED-BY-A-TEAMMATE-WAKES-NOBODY`.

**The `notify_when_idle` one-shot is the one thing that CANNOT be delegated** — accepted only from
a main conversation; `group-em-assistant` is a subagent. It stays with you if used.

**You do not relay events.** `group-em-assistant` hears its own wire and acts on it. What reaches
you is what they escalate. **The tell that you have taken the relay back: you find yourself waking
them, or working an event they already hold.**

**The park spool is `group-em-assistant`'s surface to read and triage, not yours.** Ask them for it
rather than going to the file first. **They triage and report; they never nudge a peer** — nudging
is Navi's alone, or the Group EM's own.

**Verify each clock's holder, never assume it.** `CronList` shows your tick; the check is that they
NAME the monitor's task id and the poller's resolved cadence, not that they say "armed." The held
poller's cadence is floored 5 s and ceilinged 300 s.

**Both clocks, deliberately.** A poll and an event watch fail differently. Entry covers both, and
never arms one twice. Prefer the clock that cannot be spent — a one-shot fires once per peer and
leaves it unwatched, so re-arming it per peer per tick is required, not duplication.

**A Group EM holding neither teammate is not hypothetical.** Worked case:
`coordinator/docs/wiki/group-em-entry-teammates.md`.

### Liveness instruments — two sanctioned, one banned, and you read the banned one constantly

**`ListAgents`' `busy`/`idle` IS the harness registry's `status`, banned as an input to any
liveness, reachability, or claim verdict.** `idle` means unknown, never quiet. Measurements:
`coordinator/docs/wiki/group-em-assistant-remit.md` § Liveness. Tripwire:
`LISTAGENTS-BUSY-IS-A-BANNED-LIVENESS-INPUT`.

**Sanctioned, exhaustively: the oracle's verdict, and `last_tick_at` age in
`state/group-em-watch.json`**, compared against the record's own `next_expected_by` rather than a
fixed threshold. Do not shape this as a process-table check — `pgrep -f` cannot read Windows
process command lines, and the watch runs under two different command lines besides. **Resource-usage
proxies (CPU, memory, I/O) are banned for the same reason `busy`/`idle` is** — "progress toward a
known end" is what a liveness verdict certifies, and a process burning CPU is not a process making
progress. Full rationale: `coordinator/docs/wiki/group-em-assistant-remit.md` § Liveness.

**When a PM reports the watcher is dead, do not confirm it from the session list.** `idle` is
`group-em-assistant`'s normal state between polls. Answer from `last_tick_at` age and name the
instrument.

### Every tick declines in writing, and stamps it to disk

**Each tick records a DECLINATION for every roster entry it does not message** — which gate failed
and why.

**And each tick STAMPS them to disk**, via the **engine's** `cron`/`monitor` writer,
`<engine_root>/coordinator_core/group_em/watch_heartbeat.py :: stamp(repo_root, holder_session_id,
declinations, interval_seconds, subscribed_peers=…, tick_source=…, writer_session_id=…)` — a
different function from this skill's own `watch_heartbeat.py :: stamp`, which `_stamp_watch` in
`group-em-enter.py` calls for the `entry` tick. Copy the ENGINE copy's order: `declinations` is the
THIRD positional and `interval_seconds` the fourth and required. `writer_session_id` is a keyword,
**optional in the signature and required at runtime** — it is YOUR session id, not
`holder_session_id` when a delegate arm stamps on the standing holder's behalf. `tick_source` is `cron` or
`monitor`, a KEYWORD, never positional. `declinations` is THIS tick's rows only, `[]` if none.
`subscribed_peers` is the count your `Monitor` arm is *still* subscribed to right now.

**The wake has a producer; you arm nothing for it.** `state/group-em-watch-spool.jsonl` gets one
record per park, appended by every session's own `Stop`
(`coordinator/hooks/scripts/group-em-park-spool.py`) when its park verdict lands. It is a hook, so
it needs no entry step and no holder. The engine plane commits to the spool retaining at least the
last 30 minutes of parks.

**A watching session goes idle exactly like the sessions it watches** — that is what the clock is
for. A Group EM who looks only when the PM asks has made the PM the watcher.

**What the watch is FOR:** sessions asking permission for EM-autonomous acts they already
recommended; break-class defects handed up as "worth your eye"; a session idling on a peer repo
while holding a repo-agnostic fallback it identified itself. **Not** finding sessions something to
do.

**Run the altitude test on the way OUT of a turn, not only when deciding to intervene.** *"This
session has been idle 35 minutes, do you want it doing something?"* is the canonical shape, and it
is the EM's call.

## The drive loop — what you are driving peers TOWARD

Nudging is the mechanism; this is the goal. The Group EM owns four of these five steps — **step
4's clear is the PM's act**, the one exception.

1. **Drive to execute.** A reviewed plan sitting on execution authorization is yours to release.
2. **Drive to workstream-complete.** Toward the close, not merely away from idleness.
3. **Troubleshoot alongside them until the primary exit criterion is met** — a different act from
   nudging. Stays inside the no-authoring boundary.
4. **When the ceremony completes, the PM clears them.** Only a successfully completed ceremony
   establishes out-of-work — a peer's own "I'm done" does not. `/clear` is a human act you cannot
   issue to a peer. A session at this point is **done and awaiting clear**, never your failure —
   say so plainly, finished sessions read it as loss and hesitate otherwise.
5. **Assign something new from the daily priority set.** PM-owned and per-day; ask for it if you
   do not have one.

Two worked cases, both expensive: `coordinator/docs/wiki/group-em-standing.md` § A self-reported
close is not a ceremony. Tripwire: `A-SELF-REPORTED-CLOSE-IS-NOT-A-COMPLETED-CEREMONY`.

**No step here is discharged by an artifact, and your own report cannot show the gap** — re-read
this section deliberately rather than expecting to be told.

## No registration ceremony, no persistence

Nothing is written on invoke, nothing cleaned up on exit. No roster, address, or reachability fact
for any peer is persisted anywhere. Every fact is re-derived live, every time.

**One carve-out: the send log.** `build_send_digest` appends to
`state/subagent-share/<this-session-id>/group-em-send-log.jsonl` — a record of this session's own
offers. Session-scoped, so a new Group EM starts with an empty cooldown.

## DACI is a frame, not a registry

A `/group-em` session **is** that repo's Driver for as long as it runs. Do not build a Driver
registry or roster.

## Stale-read discipline

Peer state is re-read immediately before acting on it, never from a snapshot taken earlier in the
turn — by re-entering the mode, and **never** by calling the entry op a second time inside one tick
(§ Send pass step 1).

## Collision check — discharged, cited not re-run

The platform-vocabulary collision check on `group-em` is **already discharged clean**
(`state/roadmap/gem-2026-08-14/research-corpus/group-em-skill-scaffold.md`). Nothing above re-runs
it.

## Gating granularity — entry AND per send

**Entry stays PM-gated** by this file's prefix convention: who may enter the mode at all.

**The send is gated separately, per send, and entry-gating never satisfies it.** The send is where
the `ask-before-external-action` question lives, at the PM's own bar, justified by **cost to the
receiver**, never the sender's convenience.

### Standing check

**Confirm this session still holds the nomination**: `<plugin-root>/bin/group-em-nomination.py who
--repo <root> --json` (read-only). Never re-run `group-em-enter.py` to answer this — it re-claims
and re-arms the send digest's cooldowns (§ Send pass step 1).

## Read pass (gem-13)

The enumerate-and-classify ladder lives in `read_pass.py` beside this file, invoked through §
Entry's op rather than imported. `build_roster(repo_root)` for the classified population,
`build_candidate_roster(repo_root)` for the paused-only shortlist. It excludes the caller, never
writes or sends. Full ladder: that file's module docstring.

## Send pass (gem-14)

`send_pass.py` turns `build_roster`'s **full** population into **one digest per invocation**
(`build_send_digest`). It selects and throttles; **it does not send.** Rationale:
`docs/decisions/DR-group-em-send-narrows-on-the-obligation-ledger.md`.

**`roster` IS NOT THE POPULATION — it is the shortlist**, `build_candidate_roster`'s output. A
human adjudicates it. `undischarged_obligations: None` means no ledger exists, never that the peer
owes nothing.

**Compare `roster_considered` — the enumerated count entry reports top-level — against the room,
never `len(roster)`.** A `roster` smaller than `roster_considered` is NORMAL; a `roster_considered`
smaller than the sessions you know are running is `unknown`, never quiet. Worked case:
`coordinator/docs/wiki/group-em-assistant-remit.md` § The roster is not the population.

Two settling reads: `claude agents --json`, and `python3 -m coordinator_core.group_em.idle_report
--repo-root <root> --group-em-session-id <your sid>`. Pass `--group-em-session-id` even though the
CLI accepts its omission silently — omitting it degrades offer-log suppression rather than erroring.

**Ledger rows can arrive from the engine plane.** This plane is the ledger's sole writer; the
engine appends to `state/subagent-share/<sid>/obligations-inbound.jsonl` and entry folds every
session's intake before the digest ranks. Contract:
`coordinator/docs/wiki/obligations-inbound-intake.md`. Tripwire:
`A-SECOND-WRITER-TO-A-REWRITTEN-FILE-LOSES-ROWS-SILENTLY`.

**Procedure, per invocation:**

1. § Entry's op already built both plus a `baseline` delta. **Act on that payload — do not re-run
   the entry op to refresh it**, since `build_send_digest` arms cooldowns as it emits.
2. Present it. `suppressed` says why each peer was held. `truncated` means re-evaluated next tick.
   `unrecorded` means the cooldown write failed.
3. **Per entry you intend to message, declare both gates in prose before sending:**
   - **GATE 1 (message).** Is the shared contract itself the unknown, needing round-trips — or is
     this a settled ask? A settled ask is a memo.
   - **GATE 2 (receiver).** Cheaper to them now than later? **GATE 2 has no instrument** — it rests
     on what you already know about that peer.
   - **Either gate unclear → the memo channel.** Not a degraded mode.
4. **Re-resolve the address from the SESSION ID immediately before sending, and treat a refusal as
   a refusal.** `send_pass.resolve_addressee(repo_root, peer_session_id)` returns the name that
   session answers to right now, or `None` — do not send on `None`.

   **Resolve from the id, never validate the name** — the id is stable, the name is volatile.
   Tripwire: `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

   `None` covers four cases: absent from roster, no name on the row, the roster read failed, or an
   ambiguous name. **It does NOT filter by repo** — a name resolving outside this repo comes back
   clean; carry that gap yourself.

**Never loop over `entries` sending.** `SendMessage` is in `allowed-tools`; the gate is this
paragraph.

**A `PAUSED:away` peer is never offered**, reported as `never-send-reason`. Tripwire:
`A-PAUSED-ROSTER-IS-NOT-A-NUDGE-LIST`.

## The escalation screen — a claimed PM item is presumed yours until it survives

**When a session says it has something for the PM, it is wrong about 19 times in 20** — the PM's
own measured prior. Treat "this needs the PM" as a claim to test, never routing already done.

- **"Next: review."** The next step in a procedure the session owns. Push it — unless the plan is
  small enough that review is not a step at that size, in which case name the actual next step
  instead. Mirror anti-pattern: do not grant a permission the session already holds.
- **"Variable `x` or `xy`?"** Engineering, decided by whoever holds the file. Push it — do not
  answer it either.
- **"Do I execute?"** The one with a real question, answerable by you — below.

**This is a model disposition, not a peer failing.** Say so when you push, and push anyway.

### Push, do not nudge

**"Do you need anything?" is a failure, not a gentler success.** It hands the decision back to the
session that already froze on it. Same for "want me to...?", "let me know if...".

A push **names the act, names its owner, and closes**: *"That is yours. Do X."* No question mark,
no offer, no conditional. Give the reason in one clause so the correction generalises.

You are not pushing anyone past a gate their own skill names — a gate is a considered refusal with
a named reason; hesitation is the absence of one. Push the second, never the first.

### "Do I execute?" — yours to answer, with a viability read

The PM has delegated this call. **Do not read the plan into your own context to make it.** Dispatch
`coordinator:staff-eng` for a viability read.

**This does NOT route around the rubric.** Where a plan needs the formal `execution_authorized_by`
stamp, § Delegated approve-for-execution is the only path. This lighter call answers *"should I get
on with it"* for work that does not need that stamp.

## Delegated approve-for-execution procedure

The Group EM may take the PM's execute-plan turn on one condition: the plan is
reversibility-eligible and a rubric-scored judgment against its own prime exit criterion clears a
locked threshold (8 of 8, no dimension scoring 0).

1. **Standing check** (§ Standing check).
2. Run `<plugin-root>/bin/plan-reversibility-eligibility.py <plan-path> --json` (C9). `eligible:
   false` → escalate per the threshold page's shape, stop, do not dispatch. This CLI is the single
   source of truth.
3. Confirm the plan's falsifier baseline shows the prime exit criterion false **and that a blinded
   `coordinator:exit-criterion-falsifier` authored it**:
   - **Content.** Absent or already true → escalate, stop.
   - **Provenance.** A self-authored baseline satisfies "shows the criterion false" perfectly and
     voids the guarantee. Provenance lives in the plan BODY, a prior
     `state/review-trail/approvability/` record, or this session's own dispatch of the falsifier.
     **If none of the three establishes it, treat it exactly as a missing baseline and dispatch.**
   - **Instrument soundness.** A FALSE baseline proves the criterion false, never the instrument
     sound. Ask: **what would have to be true for this to print TRUE, and is any of it reachable in
     the world the fixture builds?** Unreachable → escalate with that reason named.
   Tripwires: `A-SELF-AUTHORED-FALSIFIER-SATISFIES-THE-CHECK-AND-VOIDS-IT`,
   `A-FALSE-BASELINE-PROVES-THE-CRITERION-FALSE-NOT-THE-INSTRUMENT-SOUND`,
   `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.
4. Dispatch the named Opus persona (the PM's chosen reviewer, at the PM's chosen effort) with the
   plan path and the rubric (`coordinator/schemas/plan-approvability-rubric.json`) and nothing else.
   Authorship blinding is a hard constraint.
5. Write the judgment record (`state/review-trail/approvability/<YYYY-MM-DD>-<plan-slug>.json`) and
   validate it with C9's `--validate-record` before treating it as final.
6. On `approve`: first refuse if `execution_authorized_by` is already present with any value — a
   plan the PM already authorized needs no delegated approval. Otherwise `review-exec-auth-stamp
   stamp <plan-path> --by "GROUP-EM:<session-id>" --append-note "<record-path>"`. On `escalate`,
   emit per the threshold page's shape — do not stamp.
7. **The stamp carries a standing offer: you produce criterion evidence the plan's author should
   not.** When a plan's terminal evidence is a live act rather than a test run, offer to perform it
   as the Group EM and let the author verify. Where the separation is not free, say so and let it
   go. Tripwire: `THE-AUTHOR-OF-A-CRITERION-IS-THE-WORST-PRODUCER-OF-ITS-EVIDENCE`.

## Inbox-blitz delegation

The Group EM may execute `/workday-start` Step 1.45a's inbox blitz on this repo's behalf.

1. **Standing check** (§ Standing check) must name this session.
2. Execute Step 1.45a's procedure as written, dispatching `coordinator:group-em-assistant` per
   `dispatches[]` entry. 1.45a owns the assembler invocation, tri-valued `state` handling
   (`skipped` = no dispatch), ~30-memo shard grain, verbatim `brief`/`memos[]` passing,
   verify-rides-with-triage, the two EM-added verify checks, the manifest-race caveat, and wave
   pacing. None of it is restated here.

## Anti-scope

- **No auto-send.** `send_pass.py` selects and throttles; it holds no transport. Every send is an
  explicit per-send act with both gates declared. An unattended sender, a loop that messages each
  digest entry, or any `Stop`-registered trigger is out of scope.
- **Mandating that the watcher EXISTS is not mandating that it sends unattended.** Navi nudging on
  an observed registry transition is the "concrete observed signal" shape the ban preserves; a tick
  that messages everyone it can see is the shape it forbids. A session given a timing predicate
  re-derives `runtime-tripwire-stop-watcher.py` (681 fires / 26 days / ~99.4% wrong) one level down.
- **That ban is about AUTOMATION, never attentiveness.** A holder re-deriving the roster each turn
  and judging it is the opposite mechanism and is what the ban preserves.
- This skill does not implement the read-pass ladder or receiver-state consumption logic — supplied
  separately and integrated by reference.
- **The two dispatch grants at the top of this file are each scoped to their own named dispatch.**
  Raising the approvability judge and `group-em-assistant` under this session's own authority is
  the grant. What stays gated is that `/group-em` otherwise messages **peer sessions in their own
  windows** — an `ask-before-external-action` question no dispatch grant dissolves.
- `/autonomous` supplies the mode-shaped naming precedent only. Its `/tmp` sentinel is durable state
  and is not borrowed.
