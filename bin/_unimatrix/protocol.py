"""Peer contract and cross-session wire protocol shared by Unimatrix router and adapters.

Defines the peers.json schema, cross-session frame build/parse, reply label, provenance stamp,
and box/agent row helpers. Stdlib-only and inert on import.
"""
import json
import re
import uuid
from pathlib import Path

from _unimatrix.paths import box_id, is_ip_literal, local_box, safe_alias

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


def owned_codex_address(row, target, expected_box=None):
    """Validate/project the engine's address; never allocate or reconstruct it."""
    if not isinstance(row, dict) or "address_version" not in row:
        return None
    try:
        canonical = isinstance(target, str) and str(uuid.UUID(target)) == target
    except ValueError:
        canonical = False
    name, box = row.get("name"), row.get("box")
    match = (re.fullmatch(r"[a-z0-9][a-z0-9-]{0,19}-codex-[a-z0-9][a-z0-9-]{0,11}-([1-9][0-9]{0,18})", name)
             if isinstance(name, str) else None)
    if not (type(row.get("schema_version")) is int and row["schema_version"] == 1
            and row.get("provider") == "codex" and canonical and row.get("session_id") == target
            and type(row.get("address_version")) is int and row["address_version"] == 1
            and isinstance(box, str) and box.strip() and match and len(name) <= 64
            and int(match[1]) <= (1 << 63) - 1
            and (expected_box is None or box.casefold() == expected_box.casefold())):
        raise PeerConfigError(f"invalid engine-owned Codex address for {target!r}")
    return {key: row[key] for key in ("schema_version", "provider", "session_id", "address_version", "name", "box")}


def read_codex_address(directory, target, expected_box=None):
    """Read only the canonical UUID's engine binding; missing legacy data is absent."""
    try:
        if not isinstance(target, str) or str(uuid.UUID(target)) != target:
            return None
    except ValueError:
        return None
    try:
        row = json.loads((Path(directory) / f"{target}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise PeerConfigError(f"cannot read engine address for {target}: {exc}") from exc
    if isinstance(row, dict) and "ended_at" in row:
        raise PeerConfigError(f"engine Codex binding is ended: {target}")
    return owned_codex_address(row, target, expected_box)


def mirror_addresses(row):
    """Addresses carried by a mirror, including a short Machine-a hostname."""
    own = row.get("name")
    far = row.get("unimatrixFarName")
    addresses = [own, far]
    if row.get("unimatrixMirror") and isinstance(row.get("unimatrixMirrorName"), str):
        # A pushed mirror (relay register_name) carries no far name; its bare registered name is the
        # session's address, or a bare send fails whenever the roster's own mirror row is absent.
        addresses.append(row["unimatrixMirrorName"])
    if isinstance(own, str) and "." in own and any(row.get(key) for key in ("unimatrixRemote", "macSocketPath", "unimatrixBox")):
        # A box restart flips the label between `<name>.<box>.local` and `<name>.<box>`; both reach the session.
        addresses.append(own[:-len(".local")] if own.lower().endswith(".local") else own + ".local")
        # A pushed mirror named before the `.local` strip carries `<name>.<box>-local`; that still reaches the session.
        stem, dot, label = own.partition(".")
        if dot and label.lower().endswith("-local") and len(label) > len("-local"):
            addresses.append(f"{stem}.{label[:-len('-local')]}")
    return addresses


def projected_addresses(row):
    """Extra pickable addresses only from a validated owned projection, including mirrors."""
    if not isinstance(row, dict) or row.get("vendor") != "codex":
        return []
    try:
        owned = owned_codex_address({**row, "name": row.get("unimatrixFarName") or row.get("name")}, row.get("target"))
    except PeerConfigError:
        return []
    aliases = row.get("aliases", [])
    if not owned or not isinstance(aliases, list) or not all(safe_alias(alias) for alias in aliases):
        return []
    return [row["target"], f"codex-{row['target']}", *aliases]


def load_peers(path):
    """Read peers.json into [{name, vendor, target}], keeping a valid codexPid/codexProcStart."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("peers") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise PeerConfigError(f'{path}: expected a list of peers or {{"peers": [...]}}')
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
        if "address_version" in row:
            if peer["vendor"] != "codex":
                raise PeerConfigError("engine-owned Codex address requires vendor codex")
            peer.update(owned_codex_address(row, peer["target"]))
        if "aliases" in row:
            aliases = row["aliases"]
            if not isinstance(aliases, list) or not all(safe_alias(alias) for alias in aliases):
                raise PeerConfigError(f"{path}: invalid peer aliases")
            peer["aliases"] = list(dict.fromkeys(aliases))
        pid, started = row.get("codexPid"), row.get("codexProcStart")
        if type(pid) is int and pid > 0:
            peer["codexPid"] = pid
            if isinstance(started, str) and started:
                peer["codexProcStart"] = started
        if peer["name"] in seen:
            raise PeerConfigError(f"{path}: duplicate peer name {peer['name']!r}")
        seen.add(peer["name"])
        for address in [peer["name"], *peer.get("aliases", [])]:
            owner = (peer["vendor"], peer["target"])
            if address in addresses and addresses[address] != owner:
                raise PeerConfigError(f"{path}: alias conflict for {address!r}")
            addresses[address] = owner
        peers.append(peer)
    return peers


def parse_inbound(frame):
    """Return (sender_endpoint, sender_name, body) from a received frame dict."""
    sender = str(frame.get("from", "")).removeprefix("uds:")
    content = frame.get("message", {}).get("content", "")
    m = wrapper_re().match(content)
    body = m.group(1) if m else content
    name = _from_name_re().search(content)
    return sender, (name.group(1) if name else sender), body


def intended_receiver(frame):
    """The receiver (a session name or role) a frame names in its wrapper's `to-name`, else ''."""
    m = _to_name_re().match(str(frame.get("message", {}).get("content", "")))
    return m.group(1) if m else ""


def role_of(name) -> str:
    """The role a session name carries: its name without box label and trailing id segment."""
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
    """Cross-session user frame carrying `text` from `from_endpoint` (a socket path or pipe)."""
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
    """Return a copy of `frame` with a `provenance` object and `from_name` set to the peer name."""
    out = dict(frame)
    out["provenance"] = {"peer": peer, "vendor": vendor, "target": target,
                         "router_pid": router_pid, "msg_id": frame.get("msg_id")}
    if from_box:
        out["provenance"]["box"] = from_box
    out["from_name"] = peer
    return out


def agent_row(entry, local_box_name):
    """Roster row {name, box, vendor, this_box} from one session entry."""
    sid = str(entry.get("sessionId") or "")
    vendor = entry.get(VENDOR_FIELD) or ("peer" if sid.startswith("peer-") else "claude")
    box = entry.get(BOX_FIELD) or local_box_name
    return {"name": entry.get("name"), "box": box, "vendor": vendor, "this_box": box == local_box_name}


def self_row(entries, session_id, local_box_name):
    """The agent_row of the entry whose `sessionId` equals `session_id` exactly, else None."""
    if not session_id:
        return None
    for entry in entries:
        if entry.get("sessionId") == session_id:
            return agent_row(entry, local_box_name)
    return None


def split_by_box(rows, local_box_name, self_name=None):
    """Split agent_rows into (same, other): rows on `local_box_name` and rows elsewhere."""
    same, other = [], []
    for row in rows:
        if self_name is not None and row.get("name") == self_name:
            continue
        (same if row.get("box") == local_box_name else other).append(row)
    return same, other


__all__ = [
    "BOX_FIELD", "PROVENANCE_FIELDS", "PeerConfigError", "VENDOR_FIELD", "VENDORS",
    "agent_row", "box_id", "build_frame", "holds_receiver", "intended_receiver",
    "is_ip_literal", "label", "load_peers", "local_box", "mirror_addresses", "owned_codex_address",
    "parse_inbound", "projected_addresses", "read_codex_address", "role_of",
    "safe_alias", "self_row", "split_by_box", "stamp", "wrapper_re",
]
