---
name: box-onboarding
description: "Admit a new macOS box to the multibox fleet: Homebrew python3, Remote Login, install, engine, keys, Unimatrix, home repo, verify."
allowed-tools: ["Read", "Bash", "Glob", "Grep"]
argument-hint: "[box role: secondary | tertiary | headless]"
---

# Box Onboarding (macOS)

A one-time act, run on the box being admitted, top to bottom on a fresh macOS box. It is not a G-EM
turn: there is one network-wide G-EM, which reaches the admitted box over Unimatrix, and any box may
hold it (last writer wins across the network; `coordinator/skills/group-em/references/multibox.md`,
"One G-EM"). Onboarding gives that G-EM a box it can place work on ("Placement") and see on the
federated roster ("Federated roster"). Admission of any one job stays the target box's own verdict
("Local admission per box").

Rules: no hostname, IP, drive letter or user path is a rule; identity comes from `machine-local` and
the engine's box registry. No key body, fingerprint or vault content is ever written to a tracked file
(`coordinator/docs/wiki/multibox-key-custody.md`). The engine half is shipped; its record is
`docs/reference/new-box-engine-half.md` @ 738b91982 in the published engine (`claude-klabauter`). A step that waits on a row
not yet landed ends `GUARDED-STOP` naming that row; a stop is not a failure, record it and continue.

Transport is the home Wi-Fi LAN, or the WireGuard tunnel off-network; the exact ssh and alias config
is `coordinator/docs/wiki/unimatrix-mechanism.md`, "Transport". `<klabauter-clone>` is the engine clone
from `machine-local get repos.claude_klabauter`; `<home-repo>` is the owner's private home repo.

## Steps

1. **Homebrew python3.** Install Homebrew if absent, then python3 and git.
   - `command -v brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
   - `brew install python3 git gh` and `brew install --cask 1password-cli`
   - Done when `python3 --version` prints 3.x from `$(brew --prefix)/bin`.

2. **Remote Login.** Peers reach this box over ssh.
   - `sudo systemsetup -setremotelogin on`, then `sudo systemsetup -getremotelogin` prints `Remote Login: On`.
   - If `systemsetup` refuses for lack of Full Disk Access: System Settings > General > Sharing > Remote Login.

3. **Install coordinator-claude per `INSTALL.md`** (Steps 0-3), then clone the engine (Step 1e).
   - `claude plugin list`; done when `coordinator-claude` is listed after a restart.

4. **Engine: clone, setup, probe.** `<klabauter-clone>` exists from step 3.
   - `python3 <klabauter-clone>/scripts/setup.py --i-am-agent`, then
     `python3 <klabauter-clone>/scripts/setup.py --check --i-am-agent`.
     Done when the last prints `check: all items verified`. Engine deps land in
     `<settings-home>/engine-site` (no venv); never `--break-system-packages`.
   - **Capability probe (shipped):** `python3 -m coordinator_core.group_em.box_probe` writes `capability`
     (`os`, `arch`, `cpu_count`, `ram_mb`, `python`, `gpu`, `has_p4`, `has_ue`) into
     `<home>/state/group-em/box.json`. `has_ue` is true only with `UE_ROOT` or `UNREAL_ENGINE_ROOT` set
     before the probe; a `has_ue` false box never receives UE work.
   - Placement capability: for the Mac Mini (project-rag, ue-addon, 64 GB) set `UE_ROOT`, install the
     project-rag and ue-addon, then re-run the probe so `has_ue` is true and `ram_mb` reads ~64000;
     registration (step 8) publishes that record so the G-EM can place with `groupem.box_place`.

5. **Issue keys per the custody page.** Keys are named `<role>: <from> → <to>`. Roles:
   `Unimatrix-01` is full shell, break-glass; `Unimatrix-Zero` is the comms relay only;
   `Unimatrix-02` is the project-rag tunnel only (forwarding, no shell). One key per box pair, so
   a leak's blast radius is that pair; Zero is needed one way per pair because the initiating box
   holds the inbox connection. Unimatrix-01 is a full mesh: any one box can be the controller or
   the controlled, so long as the keys authenticate. Mint every key in 1Password; never run
   `ssh-keygen` and upload the result. 1Password's CLI cannot edit SSH Key items, and a CLI import of
   an existing OpenSSH key lands unparsed, so a key is minted, not imported.
   - **PM step, before anything uses `op` (macOS):** grant Full Disk Access to Terminal (the host app
     running Claude Code) in System Settings > Privacy & Security > Full Disk Access, then restart it.
     Without it `op` app integration fails with "No accounts configured" or "operation not permitted",
     because TCC blocks the 1Password Group Containers.
   - Mint: `op item create --category 'SSH Key' --title "<role>: <from> → <to>" --vault <team-vault> --ssh-generate-key ed25519`.
   - The initiating box reads the private half to disk, mode 600:
     `op read "op://<team-vault>/<role>: <from> → <to>/private key?ssh-format=openssh" > ~/.ssh/<key-file>; chmod 600 ~/.ssh/<key-file>`.
     Read the public half the same way (`.../public key`). No key body, fingerprint or vault content
     enters a tracked file.
   - The far-side `authorized_keys` line is installed by that box's EM or G-EM (a SendMessage over the
     existing Unimatrix, or a pasted line), never by the PM by hand. `unimatrix-install.py`
     prints the exact line, absolute interpreter included. Both directions of every box pair get the
     line, each on its own far side:
     `restrict,from="<LAN /24>,<tunnel /24>",command="<absolute interpreter> <absolute relay path>"`
     (`unimatrix-mechanism.md`, "Keys"). Refuse a single-address `from=` and a bare `python3`
     interpreter; the macOS interpreter is Homebrew's `$(brew --prefix)/bin/python3` (`/opt/homebrew` on Apple silicon, `/usr/local` on Intel). Windows far side: the line goes in
     `C:\ProgramData\ssh\administrators_authorized_keys` for admin users, needs elevation, and the
     forced command names absolute paths (`command="<absolute python.exe> <absolute path>\\unimatrix-relay.py"`).
   - A re-minted key replaces the old line on the far side. Before testing, compare
     `ssh-keygen -lf` on both ends; delete the superseded private key.
     (`A-UNIMATRIX-KEY-IS-MINTED-IN-1PASSWORD-AND-VERIFIED-BY-FINGERPRINT`.)
   - DHCP reservation uses the box's private Wi-Fi MAC with the private address set to "Fixed" for
     that network, not the hardware MAC (`docs/fleet/unimatrix-fleet.md` carries the addresses).
   - This box's own engine key: `box_key.ensure_key` mints it; pin each peer's key with op
     `groupem.box_key_pin` (both directions). Pin recipe and its tests are project-rag's.

6. **Unimatrix install, on both boxes of the pair** (both directions; either box can hold the
   network's one G-EM). Skip when the boxes share a Claude account: native `/rc` is the first route
   (`A-SAME-ACCOUNT-CROSS-BOX-USES-NATIVE-RC-FIRST`). Check mode refuses outside the verified Claude
   Code range (`A-UNIMATRIX-INSTALL-REFUSES-OUTSIDE-THE-VERIFIED-CLAUDE-RANGE`); `--force` only warns.
   - Run `<plugin-root>/bin/unimatrix-install.py` through the plugin-local ladder in
     `coordinator/snippets/resolve-coordinator-bin.md` (§ CLIs with no launcher): check mode first,
     then `--install` once it prints `in verified range`.
   - Add the ssh alias block from `unimatrix-mechanism.md` "Transport" to `~/.ssh/config` and the
     alias to machine-local `unimatrix.far_boxes`. Its `HostName` is the far box's `<box>.local`
     name, never an address (`A-UNIMATRIX-FAR-BOX-ALIAS-NAMES-THE-BOX-NEVER-ITS-IP`); a Linux near
     box needs `nss-mdns`.
   - The relay key follows the custody page (`A-UNIMATRIX-KEY-IS-A-FORCED-COMMAND-RELAY-KEY`). On
     macOS its forced command names Homebrew's `$(brew --prefix)/bin/python3` by absolute path: sshd's PATH
     `python3` is the Command Line Tools stub.
   - `unimatrix-install.py --pair <alias>` pairs this box with the peer alias; it prints the line
     the far side installs.
   - **Existing-box backfill:** admitting a box means installing and verifying both directions
     against every box already on the roster, not only the new box's own. A pair holding only one
     direction gets the missing key and line now, then step 8 probes it.

7. **Clone the G-EM home (when the owner has a private home repo).** Clone `<home-repo>` into this
   box's own resolved home path (`group-em-home.py` resolves it; paths differ per box) on the same
   shared branch: one history across boxes (`A-GROUP-EM-HOME-IS-A-GIT-REPO-WITH-A-PRIVATE-REMOTE`).
   No remote (`remote_opt_out`): skip.

8. **Verify reach, then register.** From the box holding the G-EM standing, LAN first: on the home
   Wi-Fi verify over the box's LAN address with the tunnel off; try the tunnel address only when the
   LAN address is unreachable (`unimatrix-mechanism.md`, "Transport").
   - **Roster probe, both directions:** run `ssh -o BatchMode=yes <alias> roster` from each box of the
     pair to the other, for every existing box. Expect JSON lines or an empty roster and exit `0`;
     a direction that fails is not onboarded.
   - SSH no-op: `ssh -o BatchMode=yes <box-alias> true`. Expect exit `0`.
   - Tunnel pin refuses a shell: `ssh -o BatchMode=yes -i <tunnel-key> <box-alias> true` must fail.
   - Tunnel MCP initialize (the port is the tunnel's, carried only over the `Unimatrix-02` key):
     `ssh -N -L 8767:127.0.0.1:8767 <tunnel-alias>` in one shell, then
     `curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8767/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"onboard","version":"0"}}}'`
     (add the bearer-token header if the daemon requires it). Expect `200`.
     Never route compute or spawning through that port; sessions and jobs use the shell key.
   - **Register (operator act, once the box is reachable):** op `groupem.box_register` with the
     box's `{kind: ssh, host: <LAN address or tunnel endpoint>, invoke}` transport writes the
     registry row (`box_registry.ensure_identity` mints `box.json`). When the ssh transport is
     absent the relay answers through the settings-home coordinator-invoke door.
   - **Roster and placement:** op `groupem.box_roster` lists the box with its heartbeat; op
     `groupem.box_place` with `{"run": "<label>", "requirement": {"has_ue": true, "min_ram_mb": 60000}}`
     must select it.
   - **Machine-local `box.*` keys:** after registration, on the box itself, run
     `python3 -m coordinator_core.group_em.box_probe` (writes `capability` into
     `<home>/state/group-em/box.json` and prints the record), then write each key from that output.
     The engine reads `box.json` only; these keys serve the machine-local registry.
     - `machine-local set box.id <box_id>`: `box_id` from `box.json` (the registry consumes only this key).
     - `machine-local set box.os <os>`: `capability.os`.
     - `machine-local set box.ram_mb <ram_mb>`: `capability.ram_mb`.
     - `machine-local set box.has_ue <has_ue>`: `capability.has_ue` (`true` / `false`).
     - Verify: `machine-local keys` lists all four `box.*` keys; `machine-local get box.id` equals `box_id`.

9. **Record the result.** One line per step, `PASS` / `FAIL` / `GUARDED-STOP`, in the box's
   onboarding handoff; steps 5, 6 and 8 record each direction of each pair separately.
   A `GUARDED-STOP` names the row it waits on.

## After onboarding

The cross-box SendMessage test protocol lives in `references/multibox.md` ("Cross-box SendMessage");
run it once step 8 passes.
