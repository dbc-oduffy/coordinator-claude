# Unimatrix mechanism

Unimatrix is the cross-account interbox link: it lets a Claude Code session on one box
`SendMessage` a session on another box. It is named for the link, never for a box. Key custody
is `multibox-key-custody.md`; the installer and key rules are the tripwires
`A-UNIMATRIX-INSTALL-REFUSES-OUTSIDE-THE-VERIFIED-CLAUDE-RANGE` and
`A-UNIMATRIX-KEY-IS-A-FORCED-COMMAND-RELAY-KEY`. Box names, addresses and key holders are not
here; they live in the operator's private fleet record.

## Route order

First available wins (`A-SAME-ACCOUNT-CROSS-BOX-USES-NATIVE-RC-FIRST`):

1. Native `/rc` between boxes on the same account.
2. Unimatrix, for cross-account boxes.
3. The federated route over the project-rag tunnel (see `multibox.md`).

## Transport: LAN first, tunnel off-network only

Boxes on the same network reach each other directly over the LAN; the WireGuard tunnel stays off.
The tunnel exists only for a box that is off the home network. Unimatrix tooling tries a far box's
LAN address first, falls back to its tunnel address only when the LAN address is unreachable, and
never requires the tunnel to be up. An operator on the home network never has to start the tunnel
for a Unimatrix operation.

## Parts

All four ship in `coordinator/bin/` and are installed together by `unimatrix-install.py` into
`<settings home>/unimatrix`.

- **Bridge** (`unimatrix-bridge.py`): binds a local endpoint (a Windows named pipe, a unix socket
  elsewhere) that stands for a remote session. A `SendMessage` to it is forwarded through the
  relay as `send <remote-pid>`. An optional return leg runs in the same process because the local
  inbox accepts writes only from a process registered in `~/.claude/sessions`.
- **Relay** (`unimatrix-relay.py`): the forced command on the receiving box, the only thing the
  Unimatrix key can run. Modes, from `SSH_ORIGINAL_COMMAND`: `roster` (one JSON line per live
  local session, entry plus key file), `send <pid>` (deliver one message line to that session's
  socket), `inbox <name>` (register a far session and stream what is delivered to it back over
  ssh), `source` (print the relay's own text). Anything else is refused. A far box that vendors
  the relay syncs it with `ssh <key> source`, never over the full-shell key. The `authorized_keys` line uses `restrict`: no pty, no
  forwarding.
- **Inbox** (`unimatrix-inbox.py`): registers a local session on the far box through `inbox`
  mode and carries each delivered frame into the local session, rewriting `from` into the local
  namespace. The session key travels over ssh stdin only, never argv or a log.
- **Rekey** (`unimatrix-rekey.py`): makes each local mirror entry look like a session the harness
  wrote itself.
- **Roster**: the relay's `roster` output. A mirrored far session counts as detected on the
  roster, so `ListAgents` and `notify_when_idle` see it.

## Failure behaviour

`SendMessage` to a mirror succeeds once the local bridge has the message, whatever the far leg
does. On a nonzero relay ssh exit the bridge writes a delivery-failure notice (target and ssh
error) into the sender's inbox through the return leg's `write_local`, and records the send in
`<settings home>/unimatrix/deliveries.jsonl` (last 100). `unimatrix-bridge.py status` prints recent
sends as `delivered` or `FAILED`. The mirror stays on the roster; there is no probe, retry or queue.

## Mirror rules

A mirror entry is accepted only when it matches what the harness writes. Any deviation silently
blocks idle notices.

- Key file name: `<pid>.<sha256(socket path)>.key`; on Windows the hash is over the lowercased
  pipe path.
- `procStart` is a string equal to the owning process's raw start stamp (on Windows the raw
  creation FILETIME), never a number.
- Windows pipe names are `cc-msg-<32 hex>`; any other name silently blocks idle notices.
- `from` is rewritten into the receiving box's namespace at both ends.
- On unix, the registry pid is the socket listener.
- The wire: one JSON line per connection, sender writes and closes, receiver replies nothing.

## Keys

Three roles, private halves in the vault only. Each key is named `<role>: <from> → <to>`, one key
per box pair, so a leaked key's blast radius is that pair:

- **Unimatrix-01**: the full shell, break-glass. Carries nothing routine. A full mesh: any box can
  be the controller or the controlled, so long as the keys authenticate.
- **Unimatrix-Zero**: comms relay only. A forced-command relay key with the modes above; it is
  never a shell key. Needed one way per pair, because the initiating box holds the inbox
  connection.
- **Unimatrix-02**: the project-rag tunnel only. Forwarding, no shell, no relay.

Every key is pinned to its source address with `from=` in `authorized_keys`.

## One network-wide Group EM

There is one Group EM across the network, on whichever box holds the standing. It reaches the
other boxes over Unimatrix: the relay lives on the box that receives, and the holder's box bridges
that box's roster. A box without a Group EM is not missing one. Last writer wins network-wide:
`/group-em` on any box displaces the holder on any other, keyed by box plus session id, and the
displaced holder gets the release-your-watch message over Unimatrix. The unit of custody for a
box's relay is that box.

## Consumer boxes

A consumer box lacks the authoring repos and runs only the released OSS plugin and engine. It
joins Unimatrix only through the installer shipped in a release; a hand-installed relay on such a
box is interim and is replaced by the release.

## Where facts live

Mechanism and rulings: this page. Box names, LAN and tunnel addresses, key-role holders and any
interim relay: the operator's private fleet record, never a published tree. Key material: the
vault.
