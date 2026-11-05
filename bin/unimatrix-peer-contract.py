"""Peer contract shared by the unimatrix peer router and adapters.

Defines the peers.json schema, the cross-session frame (build and parse), the reply
label, the inbound prefix a peer sees, and the provenance stamp every posted frame
carries. Stdlib only: the scripts are vendored into <settings home>/unimatrix with no venv.
"""
import json
import re
import sys
import uuid

VENDORS = ("codex", "agy")
PROVENANCE_FIELDS = ("peer", "vendor", "target", "router_pid", "msg_id")


_RE_CACHE = {}


def _memo_re(key, pattern, flags=0):
    if key not in _RE_CACHE:
        _RE_CACHE[key] = re.compile(pattern, flags)
    return _RE_CACHE[key]


def wrapper_re():
    """The cross-session wrapper pattern, compiled on first use so import stays inert."""
    return _memo_re("wrapper", r"^<cross-session-message[^>]*>\n?(.*?)\n?</cross-session-message>$", re.S)


def _from_name_re():
    return _memo_re("from_name", r'from-name="([^"]*)"')


class PeerConfigError(ValueError):
    """peers.json is malformed, names an unknown vendor, or repeats a peer name."""


def load_peers(path):
    """Read peers.json into [{name, vendor, target}].

    Accepts a top-level list or {"peers": [...]}. Refuses a missing field, an unknown
    vendor, a blank name, or a duplicate name.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("peers") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise PeerConfigError(f"{path}: expected a list of peers or {{\"peers\": [...]}}")
    peers, seen = [], set()
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
        if peer["name"] in seen:
            raise PeerConfigError(f"{path}: duplicate peer name {peer['name']!r}")
        seen.add(peer["name"])
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


def label(peer, text):
    """Prefix a reply with the peer that produced it."""
    return f"[{peer}] {text}"


def build_frame(from_endpoint, from_name, text, msg_id=None):
    """Cross-session user frame carrying `text` from `from_endpoint` (a socket path or pipe)."""
    from_name = from_name.replace('"', "'")
    content = (f'<cross-session-message from="uds:{from_endpoint}" from-name="{from_name}">\n'
               f"{text}\n</cross-session-message>")
    return {"msgV": 1, "msg_id": msg_id or str(uuid.uuid4()), "type": "user",
            "message": {"role": "user", "content": content}, "priority": "next",
            "from": f"uds:{from_endpoint}"}


def stamp(frame, peer, vendor, target, router_pid):
    """Return a copy of `frame` with a `provenance` object and `from_name` set to the peer name."""
    out = dict(frame)
    out["provenance"] = {"peer": peer, "vendor": vendor, "target": target,
                         "router_pid": router_pid, "msg_id": frame.get("msg_id")}
    out["from_name"] = peer
    return out


def main(argv=None):
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
    sys.exit(main())
