---
provenance:
  - distilled: 2026-11-13
    run_id: 2026-11-13-11h40
---

# Multibox key custody

Who holds the SSH keys that let the network-wide Group EM reach other boxes, which key may do
what, and where a key may never live. This is the **SSH credential** sense of "key-custody".

## Not the fleet-grant seam

The fleet control plane uses "key-custody" for the **fleet-grant verifier seam**: the signing
authority behind `_fleet_grant.py`'s `granted | expired | revoked | tampered | unverifiable`
verdict. That seam proves a human act happened. This page governs the SSH keys that carry a
session or a tunnel between boxes. Different artifact, different owner, different failure. Name
the page when you say "key-custody"; a bare "key-custody" is ambiguous.

## One Group EM across the network

<!-- PROVENANCE: run 2026-11-13-11h40, derived from batch-48-008, batch-48-010, batch-48-011, batch-48-012 -->
There is no per-box G-EM: the PM does not set one up on each box or talk to them individually.
The G-EM on another box existed
only to establish Unimatrix; from now on there is one across the network.
The earlier
home-cluster lead / roaming two-G-EM split is replaced, not appended. Standing is last-writer-wins
across the whole network: `/group-em` on any box displaces the holder on any other box, keyed by
box plus session id, and the displaced holder gets the owed release-your-watch message over
Unimatrix. A second standing is never refused.

## The keys

| Key | Power | Held by |
|-----|-------|---------|
| `Unimatrix-02` | The project-rag tunnel only. Forwarding only: `permitopen=127.0.0.1:8767`, `command=/usr/bin/false`. Refuses a shell command and a `:22` forward. | Any box client that reaches the project-rag MCP port. |
| `Unimatrix-01` | Full shell on the target box, break-glass: for a far-box change the PM asked for, which the Group EM makes itself rather than relaying to far-box sessions or the PM. Never for reads or checks; message the live session on that box instead. Retry a timed-out port once before handing work off. | The network-wide Group EM role, from whichever box holds the standing. |
| `Unimatrix-Zero` | Comms relay only: `restrict,command=<relay script>`, no forwarding, no pty, no shell. Runs only the relay, which delivers a message to a session socket and answers receipt reads (line digests, never text). Optional; present only where Unimatrix is installed. | The network-wide Group EM role; passphrase vault-resident, never on disk in a tracked tree. |
| `Unimatrix-File` | File leg (`put`/`get`) only: `restrict,from=<LAN /24>,<tunnel /24>,command=<file script>`, its own `authorized_keys` line and vault item, peer-pinned and capped. Never the relay key; a missing file key is a typed refusal naming it, with no fallback to the relay key (`A-UNIMATRIX-FILE-LEG-USES-ITS-OWN-FORCED-COMMAND-KEY`). Optional; present only where Unimatrix file transfer is installed. | The box that initiates the transfer; one key per box pair; passphrase vault-resident, never on disk in a tracked tree. |
| `Offsite-Store` | Off-machine backup copies only: `restrict,from=<home LAN /24>,command=<gate>`. The gate allows a legacy-protocol `scp -t` into one store directory and `shasum -a 256` on a file under it; it refuses a shell, sftp, `-r`/`-f` and any other path. Writers use `scp -O`, because sftp cannot be confined to a directory by a key option. The gate script lives under the target's settings home (`unimatrix/<store>-offsite-gate.py`). | The box whose store writes the copies; one key per store and target pair. Delete is never granted; cleanup is the target box's act. |
| WireGuard peer private key | Joins one roaming box to the home LAN through the router's WireGuard server; carries IP traffic, no session or shell of its own. Optional; present only on a box that roams. | Per box (one peer key each); vault-resident, never on a page or in a tracked file. |

**Naming.** Every key is named `<role>: <from> → <to>`, with the role one of those above.
There is one key per box pair, so a leak's blast radius is that pair. `Unimatrix-Zero` is needed
one way per pair, because the initiating box holds the inbox connection. `Unimatrix-01` is a full
mesh: any box can be the controller or the controlled, so long as the keys authenticate.

The tunnel key carries MCP streamable-HTTP and nothing else. Compute and session spawning never
route through the project-rag port; they use the shell key. The comms key carries session
messages and nothing else (`A-UNIMATRIX-KEY-IS-A-FORCED-COMMAND-RELAY-KEY`); the file key carries
files and nothing else (`A-UNIMATRIX-FILE-LEG-USES-ITS-OWN-FORCED-COMMAND-KEY`).

## Custody rules

- A key may be minted locally under `<settings home>/.secrets/ssh/`, passphrase-encrypted; the
  passphrase is a 1Password Team vault item and the system of record, so the key file alone is
  useless. Unlocking 1Password is the intended gate: `ssh-agent` loads the key at login via
  `op read`, and Unimatrix waits for that unlock after a reboot. A box without `op` is refused
  naming the missing passphrase source unless the operator passes `--unencrypted-key`
  (`A-UNIMATRIX-KEY-IS-PASSPHRASE-ENCRYPTED-AND-VERIFIED-BY-FINGERPRINT`).
- **Never a key on disk in a tracked tree.** A private key, a token or a pasted key body in a
  tracked file, a plan, a handoff, a memo or a wiki page is a defect. Untracked secrets live
  under the owner's settings home, never under a repo checkout.
- A box receives only the key its role needs. A box gets tunnel-key material for
  its own client side and an `authorized_keys` line for the key it must accept; it holds a shell
  key's private half only for a pair it initiates.
- Rotation replaces the vault item first, then the `authorized_keys` line on each target, then
  deletes the old line. Revoke by deleting the line on the target.

## Placing a key on a new macOS box

The `box-onboarding` skill's key step follows this page: fetch the public half from the vault, append
it to `~/.ssh/authorized_keys` pinned `from="<LAN /24>,<tunnel /24>"` (every address the peer can come from, Wi-Fi, wired or
tunnel; e.g. `192.168.0.0/24,10.77.0.0/24`). A single Wi-Fi address breaks under per-band private addresses.
The engine mints this box's key and pins a peer's (op `groupem.box_key_pin`).
Machine-local `box.*` keys have no engine writer; the doctrine repo owns that surface.

## Ownership

| Owner | Owns |
|-------|------|
| Doctrine repo (this page) | The custody doctrine and the tripwires below. |
| Engine | Issuing and placing per-box keys; generic box-to-box SSH for spawning sessions and jobs. |
| project-rag | The pin recipe (`permitopen`, `command=`), its tests, tunnel recipe, bearer tokens. |
| Group EM role | Holding the shell key; the placement GO/HOLD terms. |

## Admission is not custody

Holding a key reaches a box; it does not admit work onto it. The target box runs its own
admission and returns the verdict (`A-REMOTE-ADMISSION-IS-THE-TARGET-BOXS-VERDICT`).

## Tripwires

- `A-BOX-KEY-LIVES-IN-THE-VAULT-NEVER-ON-A-PAGE`
  (`coordinator-tripwires/a-box-key-lives-in-the-vault-never-on-a-page.md`)
- `A-REMOTE-ADMISSION-IS-THE-TARGET-BOXS-VERDICT`
  (`coordinator-tripwires/a-remote-admission-is-the-target-boxs-verdict.md`)
- `A-UNIMATRIX-KEY-IS-A-FORCED-COMMAND-RELAY-KEY`
  (`coordinator-tripwires/a-unimatrix-key-is-a-forced-command-relay-key.md`)
- `A-UNIMATRIX-FILE-LEG-USES-ITS-OWN-FORCED-COMMAND-KEY`
  ([a-unimatrix-file-leg-uses-its-own-forced-command-key](coordinator-tripwires/a-unimatrix-file-leg-uses-its-own-forced-command-key.md))
