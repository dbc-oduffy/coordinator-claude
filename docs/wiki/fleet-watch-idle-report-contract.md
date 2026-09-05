# The idle-report contract

> What `coordinator_core.group_em.idle_report` must emit for `agents/fleet-watch.md` to run a
> whole tick without opening a file. **DoE owns this contract; claude-klabauter owns the implementation.**
> Rule: the watcher acts on the report and nothing else — a fact the report does not carry is a
> defect in the report, never a licence to go and look.

## Why the contract sits on the consumer's side

The watcher is the consumer, so the shape is the consumer's to specify. If the contract were
derived from whatever the script currently prints, every later change to the script would be a
silent change to doctrine, and the agent's instructions would drift behind it — which is the
failure this whole arrangement exists to end. A field the watcher needs is added to the script;
the watcher never grows a workaround.

The cost case is settled: hand-deriving a tick costs ~70k tokens a wake for a one-line answer, and
re-learns the clock hazards wrong at least once per restart. A script cannot drift per wake.

## Invocation

```
python -m coordinator_core.group_em.idle_report --repo-root <root> --group-em-session-id <sid>
python -m coordinator_core.group_em.idle_report --repo-root <root> --group-em-session-id <sid> --peer <sid-or-prefix>
```

`--group-em-session-id` is the Group EM's, never the watcher's — same two-id split as
`group_em.watch`, and for the same reason: it is the Group EM's offer log that decides a peer has
already been answered. A `--json` arm carries the same fields.

**`--group-em-session-id` needs an engine at or past `b584851c` on the published mirror.** The
pre-2026-09-01 spelling was `--crown-session-id`, retained engine-side as a suppressed alias, so
old text runs on a new engine — but not the reverse: this page's spelling on an engine older than
that commit is an argparse hard-error in every dispatched fleet-watch agent. A box whose mirror is
behind pins the whole tick, not one field. Verify against the engine, never against this page.

## The verdict vocabulary is closed

Every verdict maps to exactly one action. A verdict the watcher has to interpret is a verdict
that will be interpreted differently next wake.

| Verdict | Means | The watcher does |
|---|---|---|
| `between-turns` | idle under the floor | nothing; not reported per-peer |
| `watch` | past the floor, under the threshold | one report line, no send |
| `ESCALATE` | past the threshold | acts per `nudge-shape` |
| `OUT-OF-WORK` | the session recorded `workstream-complete` or `quick-wrap` | reports to the Group EM for assignment, tells the session that is happening; **never nudged** |
| `EXITED` | the session is gone, not parked | one dated row, no send; **outranks `ESCALATE`** |
| `GROUP-EM-MOVED` | the Group EM is no longer the dispatching session | stops the tick and tells the Group EM |
| `UNKNOWN` | the peer could not be classified, with the reason inline | reports it as unknown |

**`OUT-OF-WORK` is not `ESCALATE` with a different nudge.** A session that has genuinely run out
needs work assigned by the Group EM; no nudge fixes it, and the watcher never selects the work.
Collapsing the two loses the only distinction that changes who acts.

**`EXITED` outranks `ESCALATE` because a dead session and a parked one have the same content
clock.** A transcript stops growing identically either way, so from inside the instrument they are
indistinguishable — and the watcher would otherwise nudge processes that no longer exist and
re-raise the same false alarm every tick, which teaches the Group EM to skim the report. The alarm
that gets skimmed is the one that mattered.

**Deriving it: the `EXITED` Monitor event is the derivation. The clocks are not in it at all.**
That event is the harness reporting a transition it observed; every clock-based route is an
inference from the shape of a file about a process the harness already told you about. Reaching
for the inference while the assertion sits unread in a channel is the standing failure this whole
contract is a correction for.

Registry absence corroborates, and the **box-scoped** conjunction is still required, because the
Monitor sees this box only. A peer running on another machine, or one with its messaging gate off,
is absent from this box's registry and looks exactly like a corpse — the same ambiguity that
already bites baton claims, where `status: claimed` with no registry row is not proof of
abandonment. So `EXITED` requires the peer's transcript to sit under *this* repo's project
directory and the session to be absent from *this* box's registry. Anything short of both is
`UNKNOWN` with reason `liveness-unresolved`.

A stalled content clock is neither necessary nor sufficient and forms no part of the derivation.

Reporting a live peer as dead is the worse error in both directions: it makes a stopped fleet look
tidy, which is the exact outcome the watch exists to prevent.

The row is self-dating — `EXITED since <iso>`, from the last transcript record — and the summary
line carries `exited=<n>`. A row that says how long ago it happened does not read as a new alarm on
the fourth tick, and the count means a terminal state is never invisible.

**`UNKNOWN` must exist because omission must be impossible.** A peer that cannot be classified
appears as a row with its reason. A classifier that silently drops rows makes a broken instrument
and a quiet fleet emit identically — the same failure class as an exhausted one-shot subscription.

The reason is a **key from a closed set**, never free prose — `liveness-unresolved`,
`transcript-unreadable`, `no-records`, `clock-unparseable`. Prose in a machine field is prose the
agent has to interpret, and interpretation is the drift this contract removes.

## Per-peer fields

| Field | Values | Why the watcher needs it |
|---|---|---|
| `session` | session id | the only durable handle; see `address` |
| `verdict` | the closed set above | selects the action |
| `content-age` | minutes from the last record **inside** the transcript | the real clock |
| `mtime-age` | minutes from file mtime | reported for divergence only |
| `divergence` | `<n>m` or `none` | flagged when the clocks disagree past the tolerance |
| `answered-by-group-em` | ISO stamp or `no` | suppression; the watcher must not remember who it nudged |
| `nudge-shape` | `push` / `ask-which-it-is` / `assign` / `hold` | selects which of the two nudge sentences, or neither |
| `address` | `name [ref]` or `UNADDRESSABLE` | whether a send is possible at all |
| `last-said` | one line, hard-capped | the nudge's content, and the tick's token driver |
| `named-next-move` | the move, `none`, or `unresolved` | the thing a push names back |

`last-said` is capped at the emitting end, not trimmed at the reading end — an uncapped field
puts the cost back in the agent's context, which is the whole thing being removed.

## `push` is the narrow case, never the default

The oracle emits `push` **only** when it can affirmatively see a named next move **and** no named
reason for stopping. Absent either, it emits `ask-which-it-is`.

The discriminator is not "did the session name a move" — a session can name its next move and
still be sitting behind a gate it named a reason for. A gate is a considered refusal with a
reason; hesitation is the absence of one. Pushing a gate is the one harm in this role that does
not undo, so the default direction is the question.

`hold` covers both suppression (`answered-by-group-em` inside the cooldown) and a gate-shaped stop
with a named reason. `assign` appears only on `OUT-OF-WORK` and is addressed to the Group EM.

## `named-next-move` separates "named nothing" from "could not tell"

`none` means the oracle **established** the session named no next move. `unresolved` means the
predicate could not settle it. Collapsing them makes the report assert a fact it did not measure,
in the one field the Group EM reads to decide whether a session is actually stuck — the same class
of error as reporting a live peer as dead, one field down.

**A whitelist predicate can almost never emit `none`.** Matching a phrase establishes presence;
failing to match establishes nothing, because the space of ways to name a next move is open. So
under a phrase-matching predicate every non-match is `unresolved`, and `none` is emitted only where
absence is affirmatively derivable — not as the default fallthrough. Shipping the third value while
non-matches keep rendering `none` changes the vocabulary and not the lie.

**It does not reach `nudge-shape`.** `push` already requires affirmatively seeing a named move, so
both `none` and `unresolved` yield `ask-which-it-is`, unchanged. The third value buys honest
evidence for the Group EM, never a different send — and a shape set stays closed on its own rule.

## `nudge-shape` is governed vocabulary, not evidence

Every other field in a row is evidence the Group EM reads. `nudge-shape` is not — it selects which
send the watcher makes, so it is closed and governed exactly as the verdict set is: `push`,
`ask-which-it-is`, `assign`, `hold`, and nothing else. A shape the watcher does not recognise is
the watcher improvising a message to a peer, which is the highest-stakes improvisation available
to it. Adding one is negotiated before it ships, on the same standing rule as a verdict.

The evidence fields — `divergence`, `address`, `answered-by-group-em`, `report-to-group-em`,
`EXITED since <iso>`, the summary counters — carry no such constraint. They inform; they do not
select.

## A missing enrichment downgrades toward reporting, never toward sending

An enrichment that proves too expensive may be cut, and the cut named. What may **not** happen is
the affected peers silently taking a different verdict, because in this report every such fallback
lands on a *wrong send* rather than on absent information:

- No `OUT-OF-WORK` detection and those peers arrive as `ESCALATE` — so the watcher nudges a session
  that has genuinely run out, which is the one thing that section forbids outright.
- No `answered-by-group-em` and suppression is gone — so the watcher re-nudges peers the Group EM
  answered an hour ago, which is precisely the failure the two-session-id split exists to prevent,
  and it teaches the fleet to filter the watcher.

So a cut enrichment returns its affected peers as `UNKNOWN` with a reason key naming what is
missing — `out-of-work-undetected`, `suppression-unavailable`. `UNKNOWN` routes to *report it*,
which is the correct behaviour under partial information and keeps omission impossible. A degraded
report stays honest; a degraded report that sends is worse than no report at all.

## `UNADDRESSABLE` has a named disposition, not an improvisation

`address` resolves from `harness_registry.lookup(sid).name`, which returns the exact string
`SendMessage` accepts — ~6ms a lookup, cold. It is asked for every row.

`lookup()` resolves **live sessions only**, so `None` is an answer rather than a failure to
resolve; that is what makes it the registry-absence leg of `EXITED`, asked directly instead of
inferred. The caution that goes with it does not bite here but is worth carrying: read-time
resolution misses exactly the sids that block people, because a claim record outlives the session
that wrote it and a reader arriving later asks a store that has already forgotten. This report
resolves at report time about currently-relevant peers, which is the safe side of that.

`snapshot()` yields records carrying no session id, so the join looks absent from that direction.
It is not — see `A-ONE-DIRECTIONAL-PROBE-IS-NOT-A-MISSING-CAPABILITY`.

`UNADDRESSABLE` is therefore **rare, not typical**. The oracle still never guesses and **never
infers a name from the session-id prefix**, which is coincidence and already falsified in the
field.

When a peer is `ESCALATE` and `UNADDRESSABLE`: the verdict stands, `nudge-shape` is forced to
`hold`, and the row carries `report-to-group-em: true`. The watcher reports the session id upward
and the Group EM reaches it — they hold `ListAgents` and the watcher's send would have gone out
under their address regardless. The watcher does not hunt for the name.

This is the escalation most worth getting right: the peer that most needs a nudge is exactly the
one that comes back unreachable.

## Divergence is reported, never acted on

A large `content-age` vs `mtime-age` gap means something touched the file without appending. It
**never** changes a verdict, and the report never takes the minimum across the two clocks —
taking the minimum picks the corrupted one and reports a suspended fleet as fully active. The
watcher reads the flag and passes it up.

`divergence` carries a shape alongside the minutes — `fixed` (both ages climbing, offset
constant), `growing`, or `none`. A fixed offset says something touched the transcript once after
its last record and nothing has appended since, which is available without resolving a name and
without reading the registry.

**It is evidence in the row, never a verdict and never a reason key.** A key meaning "probably
terminated" is a confidence claim, and the watcher's action is identical either way — report
upward, send nothing. A distinction that does not change what the watcher does buys no action and
creates interpretation surface, which is the thing this contract exists to remove. The reason key
stays `liveness-unresolved`; the divergence shape rides beside it and the Group EM reads both.

**The shape corroborates nothing. Measured, 14 peers, 3 confirmed exits:** two of the three corpses
showed no offset, so it is **not necessary for an exit** — the direction that would have mattered.
The offset measures the interval between a session's last record and whatever touched the file
next, which is arbitrary; for most exits nothing touches it at all. The field stays because it
records something real about the file, and stays out of every derivation.

These are properties the oracle enforces. They are stated here, and in the script, and
deliberately **not** in the agent's instructions: an agent told to remember them eventually will
not.

## The floor and the threshold are enforced, and self-describing

A floor advisory to the agent is a floor that gets undercut — the measured failure was a genuine
escalation fired at 80 seconds. The script encodes them, applies them, and prints them.

The last line is the summary and is the only line the watcher must read to know it has a whole
report:

```
peers=<n> escalate=<n> out-of-work=<n> exited=<n> unknown=<n> floor=<n>m threshold=<n>m group-em=<sid> as_of=<iso>
```

Thresholds ride on that line so a report pasted into the Group EM's context explains its own
judgements without a second lookup. `as_of` is the same rule and the same instant the report dict
carries: counts without a stamp make two correct readings minutes apart indistinguishable, and the
line is what gets pasted. **One instant, one spelling** — `as_of`, once, at the end. A second name
for it beside the counts (`counts_struck_at`, `computed_as_of`) is two fields the reader must first
prove are the same.

**Every field on this line is fixed-form: a key, `=`, and a machine-legible value.** No prose, no
parenthetical gloss. A count whose meaning needs a gloss on the line has the wrong denominator —
fix the count or document it here, where the reader has room. `exited=<n>` is a bare int and counts
peers whose verdict is `EXITED`, nothing wider.

## Failure must not read as quiet

Exit `0` means a whole report was emitted, empty roster included — `peers=0` is a legible
statement, not an absence. Any non-zero exit means **no report**: the watcher says the oracle
failed, names the exit, and stops. It does not fall back to reading transcripts, and it does not
substitute a pass of its own.

## What `--peer` is for

Re-running one peer after a nudge, to see whether the state moved. It is not a cross-check: a
second opinion the agent forms by hand is the habit this contract removes. Disagreeing with the
oracle means reporting its output **and saying so** — the fix lands in the script.
