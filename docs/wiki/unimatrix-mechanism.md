# Unimatrix mechanism

Unimatrix is the cross-account interbox link: it lets a Claude Code session on one box
`SendMessage` a session on another box. It is named for the link, never for a box: ops prose says
"Unimatrix", never a box name, for the link. Key custody
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

Unimatrix tooling tries a far box's LAN address first, falls back to its WireGuard tunnel address
only when the LAN address is unreachable, and never requires the tunnel to be up.

### ssh and alias config (no ethernet: Wi-Fi LAN, tunnel off-network)

A box without a wired link joins over the home Wi-Fi LAN; the WireGuard tunnel is the off-network
fallback. One alias per far box and role, in `~/.ssh/config` on the near box (addresses come from
the private fleet record, never this page):

```
Host <box>-lan
    HostName <box>.local
    User <far box user>
    IdentityFile ~/.ssh/<unimatrix-key-file>
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 5

Host <box>-tunnel
    HostName <far box WireGuard address>
    User <far box user>
    IdentityFile ~/.ssh/<unimatrix-key-file>
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 5
```

The `<box>-lan` `HostName` is the far box's mDNS name, never its LAN address, so a DHCP change
needs no edit (the address is informational). A Linux near box needs `nss-mdns`. A far box whose
`.local` name does not resolve from the near box (a Windows far box, say) keeps the `<box>-tunnel`
alias; its fleet-page entry records how the name resolves.
(`A-UNIMATRIX-FAR-BOX-ALIAS-NAMES-THE-BOX-NEVER-ITS-IP`.)

Machine-local `unimatrix.far_boxes` lists `<box>-lan`; use `<box>-tunnel` only when it fails. The
engine's ssh transport record takes the same host (`{kind: ssh, host, invoke}`). The far side's
`from=` pin carries the LAN /24 plus the tunnel /24 (`from="192.168.0.0/24,10.77.0.0/24"`), so the
link survives the near box on Wi-Fi or wired and an address change.

## Parts

All six ship in `coordinator/bin/` and are installed together by `unimatrix-install.py` into
`<settings home>/unimatrix`.

- **Bridge** (`unimatrix-bridge.py`): binds a local endpoint (a Windows named pipe, a unix socket
  elsewhere) that stands for a remote session. A `SendMessage` to it is forwarded through the
  relay as `send <remote-pid>`. An optional return leg runs in the same process because the local
  inbox accepts writes only from a process registered in `~/.claude/sessions`. Delivery into a
  session assumes the `crossSessionInbound: accept` default (`settings-manifest.md` § Cross-Session
  Inbound).
- **Relay** (`unimatrix-relay.py`): the forced command on the receiving box, the only thing the
  Unimatrix key can run. Modes, from `SSH_ORIGINAL_COMMAND`: `roster` (one JSON line per live
  local session, entry plus key file), `send <pid>` (deliver one message line to that session's
  socket), `inbox <name>` (register a far session and stream what is delivered to it back over
  ssh), `source` (print the relay's own text). Anything else is refused. A far box that vendors
  the relay syncs it with `ssh <key> source`, never over the full-shell key. The `authorized_keys`
  line uses `restrict`.
- **Inbox** (`unimatrix-inbox.py`): registers a local session on the far box through `inbox`
  mode and carries each delivered frame into the local session, rewriting `from` into the local
  namespace. The session key travels over ssh stdin only, never argv or a log.
- **Rekey** (`unimatrix-rekey.py`): makes each local mirror entry look like a session the harness
  wrote itself.
- **Router** (`unimatrix-peer-router.py`): one per-box process that registers every live Codex
  thread (found by its thread-writer-lock) and every live agy conversation (found by its
  presence lock, plus the leg record in `<settings home>/unimatrix/agy-legs` the agy launch hook
  writes), rescanned while serving, and retires a peer when its lock goes. A
  `<settings home>/unimatrix/peers.json` entry is optional; `peers.json` wins a clash. Each is its own roster peer,
  drops empty and bare-acknowledgement frames and empty replies unanswered,
  holds one turn lock per peer, and routes any sender (a Claude session, or another peer through
  `unimatrix-peer-router.py send <peer> <text>`) to any peer. Replies go straight to the sender's
  session socket (receiver runs `crossSessionInbound: accept`), each frame stamped with
  provenance: peer name, vendor, thread or conversation id, router pid. A Codex thread with a held
  writer lock routes through `codex queue`, daemon up or not. Intra-box only; the
  bridge, relay and inbox carry cross-box traffic.
- **Roster**: the relay's `roster` output. A mirrored far session counts as detected on the
  roster, so `ListAgents` and `notify_when_idle` see it.

## Peer registration: agy and Codex

`unimatrix-install.py` seeds the hooks. Codex registers at session start with no tool call and no
restart; agy registers a pending leg at session start and goes live at the first tool call (below). Each hook prints a `systemMessage`
so the registration shows in the UI.

- **agy**: `unimatrix-agy-hook-pretool.py` is the only PreToolUse group the installer owns. It
  asks the engine's host guard first and returns a guard `deny` as-is; otherwise the
  peer-bootstrap decision applies, and a guard `ask` with a reason plus a bootstrap `overwrite`
  yields one `ask` carrying both. The fallback is `ask`, never `allow`, never `force_ask`.
  SessionStart (`unimatrix-agy-hook-sessionstart.py`) starts a pending leg: agy's SessionStart env
  carries only the conversation id, so the leg has no token. It binds its endpoint, records the
  language-server address found from the agy pid's loopback listeners (`lsof`; none on Windows),
  and queues each peer message, acking `queued` (spool at `$AGY_LEG_SPOOL` else `<conv>.queue.jsonl` beside the leg log; capped at 1 MiB, past which the sender gets `ok:false`). The first `run_command` through the PreToolUse
  rewrite relaunches the leg live (a pending leg is never current), and the live leg drains the
  queue into agy. The token is never persisted. The install path is the "Codex and agy hosts" section of the install guide.
- **Codex**: a plain `codex` TUI, started without `--remote`, is reachable; the router finds its
  thread by the thread-writer-lock. `unimatrix-codex-launch.py` (daemon, then `codex --remote`) is
  optional. Every thread start, resume, clear and fork fires
  `unimatrix-codex-hook-sessionstart.py`, which rebinds the stable peer name (`$UNIMATRIX_PEER_NAME`,
  else `codex-<cwd basename>`) to the current thread id in `peers.json`; the router rescans it.

## Failure behaviour

`SendMessage` to a mirror succeeds once the local bridge has the message, whatever the far leg
does. On a nonzero relay ssh exit the bridge writes a delivery-failure notice (target and ssh
error) into the sender's inbox through the return leg's `write_local`, and records the send in
`<settings home>/unimatrix/deliveries.jsonl` (last 100). `unimatrix-bridge.py status` prints recent
sends as `delivered` or `FAILED`. The mirror stays on the roster; there is no probe, retry or queue.

## Link health

`unimatrix-roster.py` records each far box's link in `<settings home>/unimatrix/link-state/<alias>.json`
(alias path-sanitised), written atomically: `{alias, state: "up"|"down", since: "%Y-%m-%dT%H:%M:%SZ",
reason: str}`. The record is rewritten only on a change; an absent or unreadable record reads `up`.

- One failed roster fetch (every 30 s poll) flips the box to `down`, with the fetch error as
  `reason`; one successful fetch flips it back to `up`. There is no failure-count threshold.
- The roster logs `LINK-DOWN <alias>: <reason>` / `LINK-UP <alias>` to `bridge-*.log` on the
  change only, not per failed fetch.
- The Group EM watch reads the records each tick and emits `LINK-DOWN <alias>: <reason>` and
  `LINK-UP <alias>` once per transition. Its previous-state map persists in the watch prev record, so a
  restart does not re-report a link already known down; a link already down at the first-ever tick
  is reported once, one already up is not.
- ListAgents and the mirror session files are unchanged: a down box's mirrors are not marked
  unreachable or deleted.

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

Three roles, private halves in the vault only. One key per box pair, named `<role>: <from> → <to>`:

- **Unimatrix-01**: the full shell, break-glass. Carries nothing routine. A full mesh: any box can
  be the controller or the controlled, so long as the keys authenticate.
- **Unimatrix-Zero**: comms relay only. A forced-command relay key with the modes above; it is
  never a shell key. Needed one way per pair, because the initiating box holds the inbox
  connection.
- **Unimatrix-02**: the project-rag tunnel only. Forwarding, no shell, no relay.

Every key is pinned to its source subnets (LAN /24 plus tunnel /24) with `from=` in `authorized_keys`;
the forced-command relay key is the real control.

Mint a key in 1Password with `op item create --category 'SSH Key' --ssh-generate-key ...`, then
`op read` the private half to `~/.ssh` at mode 600. Never hand-run `ssh-keygen` and upload, and
never write a key body or vault content into a tracked file. On macOS the `op` app integration
needs Full Disk Access granted to the host app running Claude Code (Terminal); until then it fails
with "No accounts configured" or "operation not permitted". That grant is a PM step, taken up
front.

The far-side `authorized_keys` line is installed by that box's EM or G-EM, by SendMessage over the
existing Unimatrix or a pasted line, never by the PM by hand. `unimatrix-install.py` prints the
exact line with an absolute interpreter, and `unimatrix-install.py --pair <alias>` pairs a box.
The forced command names interpreter and script by absolute path:

- Windows admin users: the line goes in `C:\ProgramData\ssh\administrators_authorized_keys` and
  needs elevation. The command is `command="<absolute python.exe> <absolute path>\\unimatrix-relay.py"`;
  sshd expands no `%USERPROFILE%`.
- macOS: `/opt/homebrew/bin/python3` by absolute path, because the `python3` on sshd's PATH is the
  CLT stub.

On re-mint the far side replaces the old line. Both ends compare `ssh-keygen -lf` fingerprints
before the first test, and the superseded private key is removed.

A DHCP reservation for a Wi-Fi box uses its private Wi-Fi MAC, with the private address set to
Fixed for that network, never the hardware MAC. Per-box addresses live in
`docs/fleet/unimatrix-fleet.md`.

Every ssh that uses a file key passes `-o IdentitiesOnly=yes`. Without it, a running ssh agent
(1Password's included) offers its own keys first and trips `MaxAuthTries`, and a relay send drops
silently.

## Auto-arm

A Group EM session start in the group-em home and the `/group-em` entry run
`unimatrix-autolink.py` detached. Far boxes are the ssh aliases in machine-local
`unimatrix.far_boxes`. Each alias without a live pair gets one bridge supervisor and one inbox
supervisor, on the Unimatrix-Zero key only. It exits 0 silently when unconfigured; an unreachable
far box adds one line to `<settings home>/unimatrix/autolink.log`.

## One network-wide Group EM

There is one Group EM across the network, on whichever box holds the standing. It reaches the
other boxes over Unimatrix: the relay lives on the box that receives, and the holder's box bridges
that box's roster. Last writer wins network-wide: `/group-em` on any box displaces the holder on
any other, keyed by box plus session id, and the displaced holder gets the release-your-watch
message over Unimatrix. The unit of custody for a box's relay is that box.

## Consumer boxes

A consumer box lacks the authoring repos and runs only the released OSS plugin and engine. It
joins Unimatrix only through the installer shipped in a release; a hand-installed relay on such a
box is interim and is replaced by the release.

## Where facts live

Mechanism: this page. Box names, addresses, key-role holders: the operator's private fleet
record. Key material: the vault.
