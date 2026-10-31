---
segment_id: multibox
class: protected
order: 10
situation: multibox
---
### Multibox — one G-EM drives N boxes

**Mechanism status** per rule: `shipped (single-box)` exists today on one box; `claude-klabauter pending`
is engine work claude-klabauter owns and DoE does not write; `after hardware` waits for the second and
third box. Box identity comes from `machine-local` and claude-klabauter's box registry, never a hostname,
drive letter or user path.

#### One G-EM

One G-EM across the whole network, reaching other boxes over Unimatrix: the PM sets up one `/rc`
session and never talks to the others. A box without a G-EM is not missing one. Any box can hold
the standing, last writer wins network-wide: `/group-em` on any box displaces the holder on any
other, keyed by box plus session id, and entry never refuses over an incumbent. The displaced
holder is owed the release-your-watch message over Unimatrix. The nominated holder is
`holder.json` (`shipped (single-box)`); network-wide nomination is engine work.

#### Federated roster

The federated roster is a feed claude-klabauter owns into `group-em-watch`: `PARKED`/`WAITING`/`GONE` plus
`last_seen`, from heartbeat records (`box_id`, `sid`, `last_tick`). Never an ssh liveness probe,
never a PID read across the wire; transport carries bytes only (`claude-klabauter pending`). Today's roster
is `claude agents --json` on this box (`shipped (single-box)`); a native `/rc` session on another
box counts as detected; any other remote session is unknown, not quiet, until the feed lands.

#### Local admission per box

Local admission: admission stays a local verdict on each target box. Placement asks the target
box, over transport, to run its own `box-memory-snapshot.py --admit-peak`, and never reads that
box's memory figures remotely. The GPU slot and bulk-writer queue are per box, on each registry
row. Tripwire: `A-BOX-MEMORY-IS-THE-KERNEL-VERDICT-NOT-A-FREE-PAGES-FLOOR`.
Local `--admit-peak` is `shipped (single-box)`;
the remote ask is `claude-klabauter pending`.

#### Placement

Two primitives, both claude-klabauter's:

- **Whole runs.** A run is `engine-ask {sizing}` plus the plan path, fired on the target box and
  landing on that box's daily branch. Never place single stages. (`claude-klabauter pending`)
- **Compute shards.** Splitting one long job is an op-level shard runner, not a Claude session.
  (`claude-klabauter pending`)

The G-EM owns the placement GO/HOLD terms and the event definition. A box marked UE/p4-absent in
the registry never receives UE work. Cockpit session spawn is a future primitive (`after
hardware`); until then a remote session is a headless `claude -p` job over the shell key.

#### The /rc walk-away contract

The /rc walk-away contract: the PM starts the G-EM as a `/rc` session and leaves. Every job is
checkpointed, resumable, and admitted on its own box. A job lacking any of the three is not
placed. A box that goes silent is `GONE` on the feed; the G-EM re-places from the last
checkpoint and tells the PM only what survives the escalation screen. (`claude-klabauter pending` for the
feed and checkpoints; the contract is the G-EM's today.)

#### Cross-box SendMessage

Route order, first available wins (`A-SAME-ACCOUNT-CROSS-BOX-USES-NATIVE-RC-FIRST`):

1. **Native same-account `/rc`.** `ListAgents` lists a same-account session on another machine
   when `/rc` is connected there, and `SendMessage` delivers to it by name. Such a session counts
   as detected on the roster.
2. **Unimatrix**, optional, for cross-account boxes: a session-socket bridge and a forced-command
   relay, installed by `coordinator/bin/unimatrix-install.py` (box-onboarding, optional step).
   The installer refuses outside the verified Claude Code range
   (`A-UNIMATRIX-INSTALL-REFUSES-OUTSIDE-THE-VERIFIED-CLAUDE-RANGE`); mechanism and rulings:
   `coordinator/docs/wiki/unimatrix-mechanism.md`; its relay key is
   `A-UNIMATRIX-KEY-IS-A-FORCED-COMMAND-RELAY-KEY` (key custody page, Tripwires).
3. **The federated route**, over the project-rag tunnel; relay stamps survive the hop
   (`claude-klabauter pending`). Transport, tunnel pin and tokens are project-rag's; never route compute
   or spawning through the project-rag port.

The typed-in path (a message typed as the PM would) is the last-resort fallback, never the
design. `notify_when_idle` crosses boxes over Unimatrix, and only there: a bridge's pipe must be
named `cc-msg-<32 hex>`, or the idle-notice send is silently refused. Native `/rc` and the
federated route carry no idle notice.

#### One G-EM across boxes

The Unimatrix install is symmetric: any box on any OS (Windows, macOS, Linux) can hold the
network-wide G-EM, and it reaches every other box's sessions and is reachable from them. Listing
sessions works in both directions on either route; idle notices cross boxes over Unimatrix.

- The G-EM owns the EMs on every box it reaches; there is no second G-EM to message.
- Moving the standing is `/group-em` on the box that should hold it. The old holder, on whichever
  box, gets the release-your-watch message over Unimatrix and stops watching.

Roster and federation are engine work (run `ask-20261031T144640-db6184`); this page authors no
engine code.

**Test protocol** (run once an ssh link exists; first leg over an existing link):

1. From the G-EM, send a message to an EM on another box through the cross-box route.
2. Confirm delivery on that box: the EM's transcript shows the message.
3. Confirm the relay stamp is intact and attributes the G-EM, not the PM
   (`UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`).
4. Have the EM reply; confirm the reply reaches the G-EM with its stamp.
5. Record delivery, stamp and reply as three separate pass/fail lines, plus a `route used` line
   (native `/rc`, Unimatrix, federated or typed-in).

#### Key custody

Key holders and pins: `coordinator/docs/wiki/multibox-key-custody.md`. A key never appears on a
page.
