# Multibox key custody

Who holds the SSH keys that let the network-wide Group EM reach other boxes, which key may do
what, and where a key may never live. This is the **SSH credential** sense of "key-custody".

## Not the fleet-grant seam

Coordinator-content-repo `coordinator/docs/wiki/fleet-control-plane.md` uses "key-custody" for the **fleet-grant verifier seam**: the signing
authority behind `_fleet_grant.py`'s `granted | expired | revoked | tampered | unverifiable`
verdict. That seam proves a human act happened. This page governs the SSH keys that carry a
session or a tunnel between boxes. Different artifact, different owner, different failure. Name
the page when you say "key-custody"; a bare "key-custody" is ambiguous.

## The keys

| Key | Power | Held by |
|-----|-------|---------|
| `Unimatrix-02` | The project-rag tunnel only. Forwarding only: `permitopen=127.0.0.1:8767`, `command=/usr/bin/false`. Refuses a shell command and a `:22` forward. | Any box client that reaches the project-rag MCP port. |
| `Unimatrix-01` | Full shell on the target box, break-glass. | The network-wide Group EM role, from whichever box holds the standing. |
| `Unimatrix-Zero` | Comms relay only: `restrict,command=<relay script>`, no forwarding, no pty, no shell. Runs only the relay, which delivers a message to a session socket. Optional; present only where Unimatrix is installed. | The network-wide Group EM role; vault-resident, never on disk in a tracked tree. |
| WireGuard peer private key | Joins one roaming box to the home LAN through the router's WireGuard server; carries IP traffic, no session or shell of its own. Optional; present only on a box that roams. | Per box (one peer key each); vault-resident, never on a page or in a tracked file. |

**Naming.** Every key is named `<role>: <from> → <to>`, with the role one of the three above.
There is one key per box pair, so a leak's blast radius is that pair. `Unimatrix-Zero` is needed
one way per pair, because the initiating box holds the inbox connection. `Unimatrix-01` is a full
mesh: any box can be the controller or the controlled, so long as the keys authenticate.

The tunnel key carries MCP streamable-HTTP and nothing else. Compute and session spawning never
route through the project-rag port; they use the shell key. The comms key carries session
messages and nothing else (`A-UNIMATRIX-KEY-IS-A-FORCED-COMMAND-RELAY-KEY`).

## Custody rules

- Both keys live in the 1Password Team vault. The vault item is the system of record.
- **Never a key on disk in a tracked tree.** A private key, a token or a pasted key body in a
  tracked file, a plan, a handoff, a memo or a wiki page is a defect. Untracked secrets live
  under the owner's settings home, never under a repo checkout.
- A box receives only the key its role needs. A box gets tunnel-key material for
  its own client side and an `authorized_keys` line for the key it must accept; it holds a shell
  key's private half only for a pair it initiates.
- Rotation replaces the vault item first, then the `authorized_keys` line on each target, then
  deletes the old line. Revoke by deleting the line on the target.

## Ownership

| Owner | Owns |
|-------|------|
| DoE (this page) | The custody doctrine and the tripwires below. |
| claude-klabauter | Issuing and placing per-box keys; generic box-to-box SSH for spawning sessions and jobs. |
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
