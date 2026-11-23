#!/usr/bin/env python3
"""Peer contract shared by the unimatrix peer router and adapters.

Defines the peers.json schema, the cross-session frame (build and parse), the reply
label, the inbound prefix a peer sees, and the provenance stamp every posted frame
carries. Stdlib only: the scripts are vendored into <settings home>/unimatrix with no venv.
"""
import ipaddress
import json
import re
import socket
import sys
import uuid
from pathlib import Path

VENDORS = ("codex", "agy", "grok")
VENDOR_FIELD = "unimatrixVendor"
BOX_FIELD = "unimatrixBox"
PROVENANCE_FIELDS = ("peer", "vendor", "target", "router_pid", "msg_id")


_RE_CACHE = {}


def _memo_re(key, pattern, flags: int = 0):
    if key not in _RE_CACHE:
        _RE_CACHE[key] = re.compile(pattern, flags)
    return _RE_CACHE[key]


def wrapper_re():
    """The cross-session wrapper pattern, compiled on first use so import stays inert."""
    return _memo_re("wrapper", r"^<cross-session-message[^>]*>\n?(.*?)\n?</cross-session-message>$", re.S)


def _from_name_re():
    return _memo_re("from_name", r'from-name="([^"]*)"')


def _to_name_re():
    return _memo_re("to_name", r'^<cross-session-message[^>]*?\sto-name="([^"]*)"')


class PeerConfigError(ValueError):
    """peers.json is malformed, names an unknown vendor, or repeats a peer name."""


def safe_alias(name) -> bool:
    return (isinstance(name, str) and 1 <= len(name) <= 64 and '..' not in name and
            re.fullmatch(r'[A-Za-z0-9_-](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?', name) is not None)


def owned_codex_address(row, target, expected_box=None):
    """Validate/project the engine's address; never allocate or reconstruct it.

    A legacy row has no address_version. A claimed versioned row that cannot
    prove its exact native target fails rather than silently acquiring a name.
    expected_box is used only when reading this host's own engine bindings.
    """
    if not isinstance(row, dict) or 'address_version' not in row:
        return None
    try:
        canonical = isinstance(target, str) and str(uuid.UUID(target)) == target
    except ValueError:
        canonical = False
    name, box = row.get('name'), row.get('box')
    match = re.fullmatch(r'[a-z0-9][a-z0-9-]{0,19}-codex-[a-z0-9][a-z0-9-]{0,11}-([1-9][0-9]{0,18})', name) if isinstance(name, str) else None
    if not (type(row.get('schema_version')) is int and row['schema_version'] == 1 and
            row.get('provider') == 'codex' and canonical and row.get('session_id') == target and
            type(row.get('address_version')) is int and row['address_version'] == 1 and
            isinstance(box, str) and box.strip() and match and len(name) <= 64 and
            int(match[1]) <= (1 << 63) - 1 and
            (expected_box is None or box.casefold() == expected_box.casefold())):
        raise PeerConfigError(f'invalid engine-owned Codex address for {target!r}')
    return {key: row[key] for key in ('schema_version', 'provider', 'session_id', 'address_version', 'name', 'box')}


def read_codex_address(directory, target, expected_box=None):
    """Read only the canonical UUID's engine binding; missing legacy data is absent."""
    try:
        if not isinstance(target, str) or str(uuid.UUID(target)) != target:
            return None
    except ValueError:
        return None
    try:
        row = json.loads((Path(directory) / f'{target}.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise PeerConfigError(f'cannot read engine address for {target}: {exc}') from exc
    if isinstance(row, dict) and 'ended_at' in row:
        raise PeerConfigError(f'engine Codex binding is ended: {target}')
    return owned_codex_address(row, target, expected_box)


def mirror_addresses(row):
    """Addresses carried by a mirror, including a short Machine-a hostname."""
    own = row.get("name")
    far = row.get("unimatrixFarName")
    addresses = [own, far]
    if (isinstance(own, str) and own.lower().endswith(".machine-a.local")
            and any(row.get(key) for key in ("unimatrixRemote", "macSocketPath", "unimatrixBox"))):
        addresses.append(own[:-len(".local")])
    return addresses


def projected_addresses(row):
    """Extra pickable addresses only from a validated owned projection, including mirrors."""
    if not isinstance(row, dict) or row.get('vendor') != 'codex':
        return []
    try:
        owned = owned_codex_address({**row, 'name': row.get('unimatrixFarName') or row.get('name')}, row.get('target'))
    except PeerConfigError:
        return []
    aliases = row.get('aliases', [])
    if not owned or not isinstance(aliases, list) or not all(safe_alias(alias) for alias in aliases):
        return []
    return [row['target'], f"codex-{row['target']}", *aliases]


def load_peers(path):
    """Read peers.json into [{name, vendor, target}], keeping a valid codexPid/codexProcStart.

    Accepts a top-level list or {"peers": [...]}. Refuses a missing field, an unknown
    vendor, a blank name, or a duplicate name.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("peers") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise PeerConfigError(f"{path}: expected a list of peers or {{\"peers\": [...]}}")
    peers, seen, addresses = [], set(), {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PeerConfigError(f"{path}: peer #{i} is not an object")
        peer = {}
        for key in ("name", "vendor", "target"):
            val = row.get(key)
            if not isinstance(val, str) or not val.strip():
                raise PeerConfigError(f"{path}: peer #{i} needs a non-empty string {key!r}")
            peer[key] = val
        if peer["vendor"] not in VENDORS:
            raise PeerConfigError(f"{path}: peer {peer['name']!r} has unknown vendor {peer['vendor']!r}")
        if 'address_version' in row:
            if peer['vendor'] != 'codex':
                raise PeerConfigError('engine-owned Codex address requires vendor codex')
            peer.update(owned_codex_address(row, peer['target']))
        if 'aliases' in row:
            aliases = row['aliases']
            if not isinstance(aliases, list) or not all(safe_alias(alias) for alias in aliases):
                raise PeerConfigError(f'{path}: invalid peer aliases')
            peer['aliases'] = list(dict.fromkeys(aliases))
        pid, started = row.get('codexPid'), row.get('codexProcStart')
        if type(pid) is int and pid > 0:
            peer['codexPid'] = pid
            if isinstance(started, str) and started:
                peer['codexProcStart'] = started
        if peer["name"] in seen:
            raise PeerConfigError(f"{path}: duplicate peer name {peer['name']!r}")
        seen.add(peer["name"])
        for address in [peer['name'], *peer.get('aliases', [])]:
            owner = (peer['vendor'], peer['target'])
            if address in addresses and addresses[address] != owner:
                raise PeerConfigError(f'{path}: alias conflict for {address!r}')
            addresses[address] = owner
        peers.append(peer)
    return peers


def parse_inbound(frame):
    """Return (sender_endpoint, sender_name, body) from a received frame dict.

    sender_endpoint is the frame's `from` without its `uds:` prefix; sender_name is the
    wrapper's from-name attribute, or the endpoint when absent; body is the unwrapped text.
    """
    sender = str(frame.get("from", "")).removeprefix("uds:")
    content = frame.get("message", {}).get("content", "")
    m = wrapper_re().match(content)
    body = m.group(1) if m else content
    name = _from_name_re().search(content)
    return sender, (name.group(1) if name else sender), body


def intended_receiver(frame):
    """The receiver (a session name or role) a frame names in its wrapper's `to-name`, else ""."""
    m = _to_name_re().match(str(frame.get("message", {}).get("content", "")))
    return m.group(1) if m else ""


def role_of(name) -> str:
    """The role a session name carries: its name without box label and trailing id segment.

    group-em-c1.machine-b -> group-em; example-stats-repo-0d -> example-stats-repo; a name with no hyphen is its own role."""
    base = str(name).partition(".")[0]
    head, sep, _ = base.rpartition("-")
    return head if sep and head else base


def holds_receiver(session_name, receiver) -> bool:
    """True when the session called `session_name` is `receiver`, by name (box label ignored) or by role."""
    base = str(session_name).partition(".")[0]
    want = str(receiver).partition(".")[0]
    return bool(want) and want in (base, role_of(base))


def label(peer, text) -> str:
    """Prefix a reply with the peer that produced it."""
    return f"[{peer}] {text}"


def build_frame(from_endpoint, from_name, text, msg_id=None, from_box=None, to_name=None):
    """Cross-session user frame carrying `text` from `from_endpoint` (a socket path or pipe).

    A non-empty `from_box` adds a `from-box` attribute to the wrapper and a non-empty `to_name` a
    `to-name` attribute naming the intended receiver; None leaves the frame unchanged."""
    from_name = from_name.replace('"', "'")
    box_attr = f' from-box="{str(from_box).replace(chr(34), chr(39))}"' if from_box else ""
    if to_name:
        box_attr += f' to-name="{str(to_name).replace(chr(34), chr(39))}"'
    content = (f'<cross-session-message from="uds:{from_endpoint}" from-name="{from_name}"{box_attr}>\n'
               f"{text}\n</cross-session-message>")
    return {"msgV": 1, "msg_id": msg_id or str(uuid.uuid4()), "type": "user",
            "message": {"role": "user", "content": content}, "priority": "next",
            "from": f"uds:{from_endpoint}"}


def stamp(frame, peer, vendor, target, router_pid, from_box=None):
    """Return a copy of `frame` with a `provenance` object and `from_name` set to the peer name.

    A non-empty `from_box` adds `provenance["box"]`; None leaves provenance at PROVENANCE_FIELDS."""
    out = dict(frame)
    out["provenance"] = {"peer": peer, "vendor": vendor, "target": target,
                         "router_pid": router_pid, "msg_id": frame.get("msg_id")}
    if from_box:
        out["provenance"]["box"] = from_box
    out["from_name"] = peer
    return out


def is_ip_literal(host) -> bool:
    """True for an IPv4 or IPv6 literal (bracketed or zone-suffixed forms included)."""
    h = str(host).strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ipaddress.ip_address(h.split("%", 1)[0])
        return True
    except ValueError:
        return False


def box_id(raw, ip_hosts=None):
    """The one box normaliser: drop any `user@`, keep the first dot label, drop a trailing `-lan`, lowercase.

    An IP literal has no host label: it maps through `ip_hosts` (ip -> member host name) to that
    host's label, and stays whole, never its first octet, when unmapped."""
    host = str(raw).rpartition("@")[2]
    if is_ip_literal(host):
        host = (ip_hosts or {}).get(host.strip("[]").lower(), host)
        if is_ip_literal(host):
            return host.strip("[]").lower()
    label = host.partition(".")[0].lower()
    return label[:-4] if label.endswith("-lan") else label


def local_box():
    """This box's id: box_id of the hostname."""
    return box_id(socket.gethostname())


def agent_row(entry, local_box):
    """Roster row {name, box, vendor, this_box} from one session entry.

    vendor: the entry's stamp, else "peer" for an unstamped `peer-` face (a router older than the
    stamp), else "claude". box: the entry's stamp, else `local_box`. this_box: box == local_box."""
    sid = str(entry.get("sessionId") or "")
    vendor = entry.get(VENDOR_FIELD) or ("peer" if sid.startswith("peer-") else "claude")
    box = entry.get(BOX_FIELD) or local_box
    return {"name": entry.get("name"), "box": box, "vendor": vendor, "this_box": box == local_box}


def self_row(entries, session_id, local_box):
    """The agent_row of the entry whose `sessionId` equals `session_id` exactly, else None.

    Never a prefix match: a short id prefix names no roster row."""
    if not session_id:
        return None
    for entry in entries:
        if entry.get("sessionId") == session_id:
            return agent_row(entry, local_box)
    return None


def split_by_box(rows, local_box, self_name=None):
    """Split agent_rows into (same, other): rows on `local_box` and rows elsewhere.

    `self_name` (from self_row) is excluded from both lists; None excludes nothing."""
    same, other = [], []
    for row in rows:
        if self_name is not None and row.get("name") == self_name:
            continue
        (same if row.get("box") == local_box else other).append(row)
    return same, other


def main(argv=None) -> int:
    """Validate a peers.json: `unimatrix-peer-contract.py <peers.json>` prints each peer or the error."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1:
        print("usage: unimatrix-peer-contract.py <peers.json>", file=sys.stderr)
        return 2
    try:
        peers = load_peers(argv[0])
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    for p in peers:
        print(f"{p['name']}\t{p['vendor']}\t{p['target']}")
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-peer-contract [-h]\nunimatrix peer-contract checker; usage: unimatrix-peer-contract <file>")
        raise SystemExit(0)
    sys.exit(main())
