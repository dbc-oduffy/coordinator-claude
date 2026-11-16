#!/usr/bin/env python3
"""Per-box peer router: register every Codex thread / agy conversation in peers.json, plus every
live agy leg record, agy presence lock and Codex thread-writer-lock, as its own roster peer and
route messages between any Claude session and any peer, or peer to peer. A discovered peer retires
when its record or lock goes; a peers.json entry wins a name or target clash.

  unimatrix-peer-router.py [--peers FILE] [--sessions-dir DIR] [--state-dir DIR] [--endpoint-dir DIR]
      Serve. Default peers file: <settings home>/unimatrix/peers.json (absent is fine); leg
      records in <settings home>/unimatrix/agy-legs are rescanned every few seconds.
  unimatrix-peer-router.py send [--as NAME] <peer> <text...>
      Ask a peer a question through the running router; prints the labelled reply.

The harness keys a registry entry and its key file by pid, so one process cannot hold M
entries. The router therefore spawns one minimal registration child ("face") per peer: the
child's pid names its entry, it binds the peer's endpoint, and it forwards every inbound frame
to the router's 0600 control endpoint. Turn locks, adapters and replies stay in the router.
Replies are stamped with provenance (peer contract) and written by the router straight to the
sender's session socket; the receiver's crossSessionInbound=accept setting removes the prompt.
A frame whose sender is itself a registered peer is answered to nobody, so two peers cannot
ping-pong; the `send` path returns the reply on its own connection instead.
Windows uses current-user-only named pipes; POSIX uses private Unix sockets.
"""
import argparse
import asyncio
import errno
import importlib.util
import json
import os
import re
import secrets
import shlex
import socket
import stat
import sys
import time
from pathlib import Path

READY_SECONDS = 15
SEND_TIMEOUT = 900
ROUTER_ENDPOINT_SEED = "unimatrix-peer-router"
FRAME_LIMIT = 1 << 22
ACCEPT_READ_SECONDS = 0.05
LEG_SCAN_SECONDS = 2
ACK_BODIES = frozenset({
    "", "ok", "okay", "k", "ack", "acked", "ack received", "acknowledged", "got it",
    "thanks", "thank you", "thx", "ty", "understood", "roger", "will do",
    "sounds good", "ok thanks", "okay thanks", "👍"})


_MEMO = {}


def here():
    """Directory holding this script, resolved on first use so import does no filesystem work."""
    if "here" not in _MEMO:
        _MEMO["here"] = Path(__file__).resolve().parent
    return _MEMO["here"]


def _memo_re(key, pattern, flags=0):
    if key not in _MEMO:
        _MEMO[key] = re.compile(pattern, flags)
    return _MEMO[key]


def label_prefix():
    """Reply-label pattern ("[peer] " / "[reply] "), compiled on first use."""
    return _memo_re("label", r"^(\[[^\]]*\]\s*)+")


def _from_agent_trailer():
    return _memo_re("trailer", r"\s*From agent \S+, not the PM\..*$", re.S)


def _load(filename, modname):
    spec = importlib.util.spec_from_file_location(modname, here() / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SIBLINGS = {}


def _sibling(filename, modname):
    if modname not in _SIBLINGS:
        _SIBLINGS[modname] = _load(filename, modname)
    return _SIBLINGS[modname]


def _roster():
    """The unimatrix-roster module, loaded on first use."""
    return _sibling("unimatrix-roster.py", "unimatrix_roster")


def _liveness():
    """The liveness module (codex_holder_live), loaded on first use."""
    return _sibling("unimatrix-liveness.py", "unimatrix_liveness")


def _contract():
    """The peer contract module, loaded on first use."""
    return _sibling("unimatrix-peer-contract.py", "unimatrix_peer_contract")


def _transport():
    """The local transport module (sockets, named pipes, process locks), loaded on first use."""
    return _sibling("unimatrix-local-transport.py", "unimatrix_local_transport")


def __getattr__(name):
    if name == "PipeServer":
        return _transport().PipeServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def default_peers_file():
    """The peers file a default invocation reads."""
    return _roster().settings_home() / "unimatrix" / "peers.json"


def default_legs_dir():
    """Where the agy launch hook writes one leg record per conversation."""
    return _roster().settings_home() / "unimatrix" / "agy-legs"


def leg_record_live(rec):
    """True only when the record's leg pid is alive and still the process that stamped `procStart`.

    A record with no procStart is not shown live: a recycled pid must never revive a dead leg.
    """
    try:
        pid, stamp = int(rec["pid"]), rec.get("procStart")
        return stamp is not None and _roster().pid_alive(pid) and _roster().proc_start(pid) == stamp
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def leg_target_live(legs_dir, target):
    """True when `legs_dir` holds a live leg record for conversation `target`."""
    try:
        with open(os.path.join(legs_dir, f"{target}.json"), encoding="utf-8") as fh:
            return leg_record_live(json.load(fh))
    except (OSError, ValueError, TypeError):
        return False


def load_leg_peers(legs_dir, taken_names=(), taken_targets=()):
    """Peers for every live agy leg record in `legs_dir`: name agy-<conversation>, target the conversation.

    A record whose leg is not live (`leg_record_live`), whose name or conversation is already
    `taken_*` (peers.json wins), or that is unreadable is skipped.
    """
    peers = []
    try:
        names = sorted(os.listdir(legs_dir))
    except OSError:
        return peers
    for f in names:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(legs_dir, f), encoding="utf-8") as fh:
                rec = json.load(fh)
            conv = rec["conversation"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(conv, str) or not conv or conv in taken_targets or not leg_record_live(rec):
            continue
        name = readable_peer_name("agy", conv, rec.get("cwd"))
        if name in taken_names:
            continue
        peer = {"name": name, "vendor": "agy", "target": conv}
        if rec.get("cwd"):
            peer["cwd"] = rec["cwd"]
        peers.append(peer)
    return peers


def default_codex_locks_dir():
    """Where Codex keeps one writer lock per live thread: $CODEX_HOME (else ~/.codex)/thread-writer-locks."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "thread-writer-locks"


def default_presence_dir():
    """Where agy keeps one presence lock per live conversation: next to its brain root (AGY_BRAIN_DIR)."""
    brain = os.environ.get("AGY_BRAIN_DIR")
    root = Path(brain).parent if brain else Path.home() / ".gemini" / "antigravity-cli"
    return root / "presence"


def readable_peer_name(vendor, target, cwd=None):
    """Stable routing name carrying vendor, repository, session identity and box."""
    cwd = os.fsdecode(cwd) if isinstance(cwd, (str, os.PathLike)) else ""
    def clean(value):
        return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")
    base = str(cwd or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if cwd:
        path = Path(cwd)
        # Match the SessionStart hook: a session in repo/Plugins/Feature belongs to repo.
        # Foreign-platform paths still retain their normalized basename as a fallback.
        if path.is_absolute():
            try:
                root = next((p for p in (path, *path.parents) if (p / ".git").exists()), None)
                if root is not None:
                    base = root.name
            except OSError:
                pass
    import hashlib
    short = hashlib.sha256(target.encode()).hexdigest()[:10]
    return f"{vendor}-{clean(base) or 'session'}-{short}-on-{clean(_contract().local_box())}"


def codex_thread_metadata(home):
    """Read available identity fields without modifying Codex's database or requiring its newest schema."""
    import sqlite3
    from contextlib import closing
    databases = []
    for db in Path(home).glob("state_*.sqlite"):
        version = re.fullmatch(r"state_(\d+)\.sqlite", db.name)
        if version:
            databases.append((int(version.group(1)), db))
    for _, db in sorted(databases, reverse=True):
        try:
            with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)) as conn:
                available = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
                columns = [name for name in ("id", "cwd", "source", "thread_source", "agent_path")
                           if name in available]
                if "id" not in columns or "cwd" not in columns:
                    continue
                return {row[0]: dict(zip(columns, row))
                        for row in conn.execute("SELECT " + ", ".join(columns) + " FROM threads")}
        except (sqlite3.Error, ValueError):
            continue
    return {}


def codex_cwds(home):
    """Thread cwd mapping retained for callers that only need repository names."""
    return {target: row["cwd"] for target, row in codex_thread_metadata(home).items()}


def codex_is_subagent(metadata):
    """Spawned child agents belong to their owner and cannot accept independently queued input."""
    if metadata.get("thread_source") == "subagent":
        return True
    source = metadata.get("source")
    if source == "subagent":
        return True
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except ValueError:
            source = None
    if isinstance(source, dict) and "subagent" in source:
        return True
    path = metadata.get("agent_path")
    return isinstance(path, str) and path.startswith("/root/")


def codex_parent_id(metadata):
    """`source.subagent.thread_spawn.parent_thread_id` of a thread's metadata row, else None."""
    source = metadata.get("source") if isinstance(metadata, dict) else None
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except ValueError:
            return None
    spawn = source.get("subagent") if isinstance(source, dict) else None
    spawn = spawn.get("thread_spawn") if isinstance(spawn, dict) else None
    parent = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
    return parent if isinstance(parent, str) and parent else None


def codex_root_parent(ident, lookup, max_depth=8):
    """Sendable root above sub-agent `ident`, walking parent_thread_id via `lookup(id) -> metadata row`.

    None when any link is unknown, cyclic, too deep, or the top is not a sendable root.
    """
    seen, current = {ident}, ident
    for _ in range(max_depth):
        row = lookup(current)
        if not isinstance(row, dict) or not row:
            return None
        if not codex_is_subagent(row):
            return current if current != ident and codex_is_sendable_root(row) else None
        current = codex_parent_id(row)
        if not current or current in seen:
            return None
        seen.add(current)
    return None


def codex_is_sendable_root(metadata):
    """Positive local identity evidence only; a held lock/address is not root proof.

    Native source='vscode', thread_source='user', agent_path=NULL is an observed
    root. CLI roots use the same user discriminator. Missing/unknown source,
    child source and contradictory fields are not independently sendable.
    """
    if not isinstance(metadata, dict) or codex_is_subagent(metadata):
        return False
    source = metadata.get('source')
    if isinstance(source, str) and source not in ('cli', 'vscode'):
        try:
            source = json.loads(source)
        except ValueError:
            return False
    if not isinstance(source, str) or source not in ('cli', 'vscode'):
        return False
    if metadata.get('thread_source') not in (None, 'user'):
        return False
    return metadata.get('agent_path') in (None, '/root')


def lock_held(path):
    """True while another process holds any flock on `path`; a free or unreadable file is not live.

    Probes with an exclusive lock so a holder in shared mode still reads as held. A missing or
    unreadable file, or any lock error other than contention, reads as not held.
    """
    try:
        file = open(path, "r+b" if sys.platform == "win32" else "rb")
    except OSError:
        return False
    with file:
        try:
            if not _transport().lock_file(file):
                return True
            _transport().unlock_file(file)
        except (OSError, ImportError):
            return False
        return False


_ROLLOUT_VERDICTS = {}


def codex_rollout_addressable(home, ident, index):
    """Second gate after codex_is_sendable_root: the thread has a rollout and it is not a sub-agent's.

    `index` is a one-element list holding the scan's rollout_index, built on first need. A thread's
    source never changes, so a verdict backed by a rollout is cached; a missing rollout is not.
    """
    key = (str(home), ident)
    if key in _ROLLOUT_VERDICTS:
        return _ROLLOUT_VERDICTS[key]
    codex = _sibling("unimatrix-peer-codex.py", "unimatrix_peer_codex")
    if not index:
        index.append(codex.rollout_index(home))
    verdict = codex.thread_addressable(ident, home, index[0])
    if ident in index[0]:
        _ROLLOUT_VERDICTS[key] = verdict
    return verdict


def codex_rollout_identity(home, ident, index):
    """Identity from the rollout's first session_meta line, for a thread SQLite has no row for.

    `index` is the scan's one-element rollout_index holder. Returns {} without positive evidence.
    """
    if not index:
        index.append(_sibling("unimatrix-peer-codex.py", "unimatrix_peer_codex").rollout_index(home))
    path = index[0].get(ident)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            row = json.loads(fh.readline())
    except (OSError, ValueError, TypeError):
        return {}
    payload = row.get("payload") if isinstance(row, dict) and row.get("type") == "session_meta" else None
    source = payload.get("source") if isinstance(payload, dict) else None
    return {"source": source} if source is not None else {}


def load_lock_peers(lock_dir, vendor, taken_names=(), taken_targets=()):
    """Peers for every held `<id>.lock` in `lock_dir`: name <vendor>-<id>, target the id.

    Lock files outlive their holder, so a file nobody holds is stale and skipped; so is a name or
    id already `taken_*` (peers.json wins) and any dotfile.
    """
    peers = []
    try:
        names = sorted(os.listdir(lock_dir))
    except OSError:
        return peers
    metadata = codex_thread_metadata(Path(lock_dir).resolve().parent) if vendor == "codex" else {}
    cwds = {target: row["cwd"] for target, row in metadata.items()}
    home, rollouts = Path(lock_dir).resolve().parent, []
    for f in names:
        ident = f[:-len(".lock")]
        if f.startswith(".") or not f.endswith(".lock") or not ident or ident in taken_targets:
            continue
        if vendor == "codex" and not codex_is_sendable_root(
                metadata[ident] if ident in metadata else codex_rollout_identity(home, ident, rollouts)):
            continue
        legacy = readable_peer_name(vendor, ident, cwds.get(ident))
        address = None
        if vendor == 'codex':
            try:
                address = _contract().read_codex_address(
                    _roster().settings_home() / 'host-sessions' / 'codex', ident, socket.gethostname())
            except _contract().PeerConfigError as exc:
                print(f'unimatrix: refusing Codex address: {exc}', file=sys.stderr)
                continue
        name = address['name'] if address else legacy
        if name in taken_names:
            if address:
                print(f'unimatrix: refusing engine alias conflict: {name}', file=sys.stderr)
            continue
        if not lock_held(os.path.join(lock_dir, f)):
            continue
        if vendor == "codex" and not codex_rollout_addressable(home, ident, rollouts):
            continue
        if vendor == "codex" and not address:
            print(f'unimatrix: refusing Codex peer without engine address: {ident}', file=sys.stderr)
            continue
        peer = {"name": name, "vendor": vendor, "target": ident}
        if address:
            peer.update(address)
            peer['aliases'] = [alias for alias in (legacy, f'codex-{ident}') if _contract().safe_alias(alias) and alias != name]
        if cwds.get(ident):
            peer["cwd"] = cwds[ident]
        if vendor == "codex":
            peer.update(_liveness().codex_thread_holder(home, ident))
        peers.append(peer)
    return peers


SEND_SCRIPT = "unimatrix-send.py"
STALE_CODEX_ERROR = "Codex peer is stale: no live attached process"
NO_REPLY_MARKERS = {"[unimatrix-peer-codex] no reply before timeout",
                    "[unimatrix-peer-grok] no reply before timeout"}
NOT_DELIVERED_PREFIXES = ("[unimatrix-peer-agy] not delivered", "[unimatrix-peer-agy] delivery failed",
                          "delivery failed:")


_MIRROR_MARKERS = ("unimatrixRemote", "macSocketPath", "unimatrixMirror", "farPid")


def _far_alias_is_stale(entry):
    """True when `entry` is a Claude mirror registered under another far session's name.

    A mirror is named `<far name>.<box>`; one whose registered name derives from a different far
    name holds a stale far-name mapping, so whichever of its two names an address matched, the
    frame would land on the session the other name denotes. Codex/agy mirrors keep their readable
    aliases and are exempt.
    """
    far, own = entry.get("unimatrixFarName"), entry.get("name")
    if (entry.get("vendor") in ("codex", "agy") or not any(entry.get(key) for key in _MIRROR_MARKERS)
            or not isinstance(far, str) or not isinstance(own, str)):
        return False
    return own.partition(".")[0] not in (far.partition(".")[0], far.replace(".", "-"))


def _ref_contradicts_session(entry, name):
    """True when `name` ends in a `[ref]` and the row it matched by that name is not the session the ref names.

    A ref is the first six hex digits of the session id; a row with no session id cannot prove it.
    """
    m = _memo_re("name_ref", r"^.+ \[([0-9a-f]{6})\]$").match(name)
    return bool(m) and not str(entry.get("sessionId") or "").lower().startswith(m.group(1))


def not_delivered(reply):
    """True when an adapter reply says the message never reached the peer."""
    return str(reply or "").lstrip().startswith(NOT_DELIVERED_PREFIXES)


def wrap_inbound(sender, body, reply_to=None):
    """What a peer sees: `[<sender>] <body>` plus a trailer naming the sender and the exact reply command.

    `reply_to` overrides the --to address when the sender itself cannot be queued (a Codex v2 sub-agent).
    """
    # Run through the interpreter, never the exec bit: Windows has none (check_posix_exec_assumptions).
    if sys.platform == "win32":
        # PowerShell call-operator form; a peer driving a POSIX shell on Windows cannot run it.
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        send = f"& {quote(sys.executable)} {quote(here() / SEND_SCRIPT)}"
    else:
        quote = shlex.quote
        send = f"{quote(sys.executable)} {quote(str(here() / SEND_SCRIPT))}"
    return (f"[{sender}] {body}\n\nFrom agent {sender}, not the PM. "
            f"Never answer them in plain text to the human at your keyboard. "
            f"Reply to them with: {send} --to {quote(str(reply_to or sender))} '<your reply>'")


def routable_from(frame, name):
    """`frame` with the wrapper's reply address (`from="uds:<face endpoint>"`) replaced by `name`.

    A face endpoint is this box's own socket or pipe, unroutable from a far box; a session name routes
    through that box's mirror. `frame["from"]` stays: the local harness checks it against the face."""
    out = dict(frame)
    msg = out.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        safe = str(name).replace('"', "'")
        out["message"] = {**msg, "content": re.sub(r'(<cross-session-message from=")uds:[^"]*"',
                                                    lambda m: f'{m.group(1)}{safe}"', msg["content"], count=1)}
    return out


def _receipt(reached):
    """`reached` / `reached_box` receipt fields for the session a send resolved to; {} when none."""
    return {"reached": reached[0], "reached_box": reached[1]} if reached and reached[0] else {}


TRANSPORT_HOP_LIMIT = 2
SLOT_RECEIVERS = frozenset({"slot", "slot-admission"})  # receivers that name the slot-admission role
SLOT_ROLE = "group-em"


def _hop_marker():
    return _memo_re("hop_marker", r"\s*\[(?:forwarded message from (?P<fwd>[^\]]*)|(?P<via>[^\]]*) via Unimatrix transport)\]")


def hop_chain(body):
    """The names that already relayed `body`, from its leading relay markers, outermost first."""
    chain, pos = [], 0
    while (m := _hop_marker().match(str(body), pos)):
        chain.append((m.group("fwd") if m.group("fwd") is not None else m.group("via")).strip())
        pos = m.end()
    return chain


def hop_count(body):
    """How many transport relay markers lead `body`: each forward wraps the body in another."""
    return len(hop_chain(body))


def is_ack(text):
    """True for an empty body or a bare acknowledgement ("ok", "got it", "thanks!"), which nobody answers."""
    t = _from_agent_trailer().sub("", str(text))
    t = " ".join(t.lower().split())
    t = label_prefix().sub("", t).strip(" .!?,;:-")
    return t in ACK_BODIES


def default_state_dir():
    return _roster().settings_home() / "unimatrix" / "router"


def endpoint_path(seed, endpoint_dir=None):
    """Endpoint for `seed`: roster.local_endpoint, or <endpoint_dir>/<hash>.sock when overridden."""
    if endpoint_dir and sys.platform == "win32":
        seed = f"{os.path.abspath(endpoint_dir)}:{seed}"
    ep = _roster().local_endpoint(seed)
    if endpoint_dir and sys.platform != "win32":
        return os.path.join(endpoint_dir, os.path.basename(ep))
    return ep


def peer_endpoint(name, endpoint_dir=None):
    return endpoint_path(f"unimatrix-peer-{name}", endpoint_dir)


def _private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)


def request_line(endpoint, request, timeout=SEND_TIMEOUT):
    """Send one JSON line to a local endpoint and return the one-line JSON answer."""
    if _transport().is_pipe(endpoint):
        raw = _transport().pipe_exchange(endpoint, (json.dumps(request) + "\n").encode("utf-8"), timeout)
        return json.loads(raw.split(b"\n", 1)[0] or b'{"ok":false,"error":"closed"}')
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    try:
        s.connect(endpoint)
        s.sendall((json.dumps(request) + "\n").encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    return json.loads(buf.split(b"\n", 1)[0] or b'{"ok":false,"error":"closed"}')


async def start_private_server(handler, endpoint):
    """Serve `handler` on a private local endpoint (current-user-only pipe or 0600 socket)."""
    return await _transport().start_server(handler, endpoint, FRAME_LIMIT)


class Registration:
    """A registry entry plus its 0600 key file for one endpoint, keyed by the writing pid."""

    def __init__(self, name, endpoint, sessions_dir, cwd=None, vendor=None, peer=None):
        native_target = None
        if vendor == 'codex':
            native_target = peer.get('target') if isinstance(peer, dict) else None
            if (not isinstance(peer, dict) or peer.get('vendor') != 'codex' or peer.get('name') != name
                    or not isinstance(native_target, str)
                    or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', native_target)
                    or peer.get('session_id') not in (None, native_target)):
                raise ValueError('Codex face requires its accepted peer native target UUID')
        self.pid = os.getpid()
        self.endpoint = endpoint
        self.sessions_dir = sessions_dir
        self.token = secrets.token_hex(16)
        self.entry = os.path.join(sessions_dir, f"{self.pid}.json")
        self.key = os.path.join(sessions_dir, _roster().key_name(self.pid, endpoint))
        now = int(time.time() * 1000)
        self.data = {
            "pid": self.pid, "sessionId": f"peer-{name}-{self.pid}", "cwd": cwd or os.getcwd(),
            "startedAt": now, "procStart": _roster().proc_start(self.pid), "peerProtocol": 1,
            "peerFeatures": [], "kind": "interactive", "entrypoint": "cli",
            "pidDomain": _roster().pid_domain(), "messagingSocketPath": endpoint, "name": name,
            "nameSource": "derived", "nameSince": now, "status": "idle", "updatedAt": now,
            "statusUpdatedAt": now,
            "vendor": vendor or "unknown", "box": _contract().local_box(),
        }
        if native_target is not None:
            # Explicit router-owned binding, also for legacy display names.
            # Do not invent an engine-owned alias, role or parent identity.
            self.data['target'] = native_target
        if isinstance(peer, dict) and 'address_version' in peer:
            address = _contract().owned_codex_address(peer, peer.get('target'))
            if vendor != 'codex' or address['name'] != name:
                raise _contract().PeerConfigError('face does not match engine-owned Codex address')
            self.data.update(address, target=peer['target'], aliases=list(peer.get('aliases', [])), nameSource='engine')

    def write(self):
        _private_dir(self.sessions_dir)
        fd = os.open(self.key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"peerToken": self.token, ("procStartFt" if sys.platform == "win32" else "procStart"): self.data["procStart"],
                       "pidDomain": self.data["pidDomain"]}, f)
            f.write("\n")
        _roster().write_json_atomic(self.entry, self.data)

    def remove(self):
        for p in (self.entry, self.key):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass


def sweep_pid_files(sessions_dir, pid):
    """Delete every `<pid>.*` registry file (the roster.unmirror naming rule), killing nothing."""
    try:
        names = os.listdir(sessions_dir)
    except FileNotFoundError:
        return
    for f in names:
        if f.startswith(f"{pid}."):
            try:
                os.remove(os.path.join(sessions_dir, f))
            except FileNotFoundError:
                pass


# ------------------------------------------------------------------ face (registration child)

async def run_face(name, endpoint, forward, sessions_dir, cwd=None, transport=False, vendor=None, peer=None,
                   owner_pid=None, owner_start=None):
    """Register `name`, take inbound frames on `endpoint`, forward each to the router.

    `owner_pid`/`owner_start` stamp the owning router's identity so a later router can reap this face.
    """
    reg = Registration(name, endpoint, sessions_dir, cwd=cwd, vendor=vendor, peer=peer)
    if owner_pid and owner_start:
        reg.data.update(unimatrixRouterPid=owner_pid, unimatrixRouterStart=owner_start)
    if transport:
        reg.data.update(unimatrixTransport=True, vendor="transport")

    async def on_conn(reader, writer):
        try:
            raw = await reader.read()
            if not raw.strip():
                return  # liveness probe
            for line in raw.splitlines():
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(frame, dict):
                    continue
                if frame.get("op") == "deliver":
                    # The receiving harness checks the connecting PID against the
                    # registration for frame.from, so the registered face must write.
                    try:
                        outgoing = frame["frame"]
                        if not isinstance(outgoing, dict) or outgoing.get("from") != f"uds:{endpoint}":
                            raise ValueError("outbound frame must originate from this face")
                        await asyncio.to_thread(deliver, frame["endpoint"],
                                                (json.dumps(outgoing) + "\n").encode("utf-8"), sessions_dir)
                        response = {"ok": True}
                    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                        response = {"ok": False, "error": f"face delivery failed: {exc}"}
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
                    return
                if frame.get("type") == "user":
                    try:
                        answer = await asyncio.to_thread(request_line, forward,
                                                         {"op": "inbound", "peer": name, "frame": frame}, 15)
                    except (OSError, ValueError) as exc:
                        answer = {"ok": False, "error": f"router unreachable: {exc}"}
                    if isinstance(answer, dict) and answer.get("ok") is False:
                        # Silence is acceptance; only a refusal is written back.
                        try:
                            writer.write((json.dumps({"ok": False, "error": answer.get("error", "not delivered")})
                                          + "\n").encode("utf-8"))
                            await writer.drain()
                        except OSError:
                            pass
                        return
        finally:
            writer.close()

    server = await start_private_server(on_conn, endpoint)
    reg.write()
    stop = asyncio.Event()
    _transport().install_stop_handlers(stop)
    try:
        await stop.wait()
    finally:
        server.close()
        reg.remove()


# ------------------------------------------------------------------ router

def default_adapters():
    """vendor -> async fn(peer, text) -> reply text, loading the adapters on first use."""
    cache = {}

    def mod(filename, key):
        if key not in cache:
            cache[key] = _load(filename, f"unimatrix_peer_{key}")
        return cache[key]

    async def codex(peer, text):
        m = mod("unimatrix-peer-codex.py", "codex")
        return await m.codex_turn(m.socket_path(), peer["target"], text, tui_held=bool(peer.get("tui")))

    async def agy(peer, text):
        m = mod("unimatrix-peer-agy.py", "agy")
        return await m.agy_turn(m.leg_endpoint(peer["target"]), m.transcript_path(peer["target"]), text)

    async def grok(peer, text):
        m = mod("unimatrix-peer-grok.py", "grok")
        if not peer.get("cwd"):
            return "delivery failed: grok peer has no cwd to pin the resume to"
        return await m.grok_turn(peer["target"], peer["cwd"], text, runner=m.subprocess.run)

    return {"codex": codex, "agy": agy, "grok": grok}


class Router:
    """Owns one face child per peer, the control endpoint and the turn locks."""

    last_refusal = ""
    last_resolved_far = False
    last_resolved_row = None  # (name, box) of the one session resolve_sender last matched

    def __init__(self, peers, sessions_dir=None, state_dir=None, endpoint_dir=None,
                 adapters=None, ready_seconds=READY_SECONDS, legs_dir=None,
                 codex_locks_dir=None, presence_dir=None, grok_home=None):
        peers = list(peers)
        self.codex_home = Path(codex_locks_dir or default_codex_locks_dir()).resolve().parent
        metadata = codex_thread_metadata(self.codex_home) if any(p.get('vendor') == 'codex' for p in peers) else {}
        self.refused_codex_addresses = set()
        accepted = []
        for peer in peers:
            if peer.get('vendor') == 'codex' and not codex_is_sendable_root(metadata.get(peer.get('target'), {})):
                self.refused_codex_addresses.update([peer['name'], peer['target'], 'codex-' + peer['target'], *peer.get('aliases', [])])
                continue
            accepted.append(peer)
        self.peers = {p["name"]: p for p in accepted}
        self.sessions_dir = str(sessions_dir or _roster().sessions_dir())
        self.state_dir = str(state_dir or default_state_dir())
        self.endpoint_dir = str(endpoint_dir) if endpoint_dir else None
        self.adapters = adapters or default_adapters()
        self.ready_seconds = ready_seconds
        self.locks = {n: asyncio.Lock() for n in self.peers}
        self.ctl = endpoint_path(ROUTER_ENDPOINT_SEED, self.endpoint_dir)
        self.log_path = os.path.join(self.state_dir, "unimatrix-peer-router.log")
        self.faces = {}  # peer name -> Popen
        self.addressed = {}  # peer name -> names it sent to during its open inbound turn
        self.server = None
        self.tasks = set()
        self.legs_dir = str(legs_dir) if legs_dir else None
        self.codex_locks_dir = str(codex_locks_dir) if codex_locks_dir else None
        self.presence_dir = str(presence_dir) if presence_dir else None
        self.grok_home = str(grok_home) if grok_home else None
        self.discovered = set()  # names found by a scan, not given at construction; only these retire
        self.scanner = None
        self.transport_sources = {}  # infrastructure face name -> registered caller name or None
        self.transport_targets = {}  # each infrastructure face is one source/destination conversation
        self.transport_lock = asyncio.Lock()
        self.lease = None  # open router.lock handle, locked for the router lifetime
        self.stop_requested = asyncio.Event()  # set by the shutdown op and by stop signals; serve waits on it
        self.pid_file = None  # router.pid.json path, set only while this router owns the lease
        self.ctl_ino = None  # inode of the control socket this router bound; None on a pipe
        self.bound_faces = set()  # face endpoints whose child registration reached ready
        self.dead_holders = set()  # Codex peers whose recorded holder is gone: no face, not listed

    def peer_stale(self, name):
        """True for a Codex peer without a live attached holder: dead (False) or unrecorded (None)."""
        peer = self.peers.get(name)
        if not isinstance(peer, dict) or peer.get("vendor") != "codex":
            return False
        return name in self.dead_holders or _liveness().codex_holder_live(peer) is not True

    async def _drop_dead_holders(self):
        """Stop the face of every peers-file Codex row whose recorded holder is gone.

        The row stays in `self.peers` so discovery still treats its target as taken; peers.json is
        never rewritten. A row with no recorded holder is unknown, not dead, and keeps its face.
        """
        for name, peer in list(self.peers.items()):
            if peer.get("vendor") == "agy" and self.legs_dir and name not in self.discovered:
                if leg_target_live(self.legs_dir, peer.get("target")):
                    self.dead_holders.discard(name)
                    continue
                if name in self.dead_holders:
                    continue
                self.dead_holders.add(name)
                if name in self.faces:
                    await self._stop_face(name)
                self.log("leg-gone", name)
                continue
            if (peer.get("vendor") != "codex" or name in self.discovered or name in self.dead_holders
                    or _liveness().codex_holder_live(peer) is not False):
                continue
            self.dead_holders.add(name)
            if name in self.faces:
                await self._stop_face(name)
            self.log("holder-gone", name)

    def log(self, *a):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
        except OSError:
            pass

    def endpoint_of(self, name):
        return peer_endpoint(name, self.endpoint_dir)

    def peer_endpoints(self):
        return {self.endpoint_of(n) for n in self.peers}

    # -- lifecycle

    async def _wait(self, what, ready, proc=None):
        deadline = time.monotonic() + self.ready_seconds
        while not ready():
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"{what} exited with {proc.returncode} before it was ready")
            if time.monotonic() > deadline:
                raise RuntimeError(f"{what} not ready within {self.ready_seconds}s")
            await asyncio.sleep(0.05)

    async def start(self):
        try:
            _private_dir(self.state_dir)
            if sys.platform != "win32":
                _private_dir(os.path.dirname(self.ctl))
            self.lease = open(os.path.join(self.state_dir, "router.lock"), "a+b")
            if not _transport().lock_file(self.lease):
                self.lease.close()
                self.lease = None
                raise RuntimeError("peer router already owns the local endpoint")
            self.pid_file = os.path.join(self.state_dir, "router.pid.json")
            _roster().write_json_atomic(self.pid_file, {"pid": os.getpid(),
                                                         "procStart": _roster().proc_start(os.getpid())})
            self.server = await self._bind_control()
            self.ctl_ino = self._ctl_inode()
            await asyncio.to_thread(self._reconcile_orphan_faces)
            await self._drop_dead_holders()
            for name in list(self.peers):
                if name not in self.dead_holders:
                    await self._spawn_face(name)
            if self.legs_dir or self.codex_locks_dir or self.presence_dir or self.grok_home:
                await self.refresh_discovered()
            self.scanner = asyncio.create_task(self._scan_discovered())
        except BaseException:
            await self.stop()
            raise

    def _live_discovered(self):
        """name -> peer for every live agy leg, agy presence lock and Codex writer lock.

        Peers given at construction (peers.json) are `taken`: they win a name or target clash.
        """
        fixed = [p for n, p in self.peers.items() if n not in self.discovered]
        names = {p["name"] for p in fixed}
        targets = {p["target"] for p in fixed}
        live = {}
        owned = {p['target']: p for n, p in self.peers.items()
                 if n in self.discovered and p.get('vendor') == 'codex' and p.get('address_version') == 1}
        scans = []
        if self.legs_dir:
            scans.append(lambda tn, tt: load_leg_peers(self.legs_dir, tn, tt))
        if self.presence_dir:
            scans.append(lambda tn, tt: load_lock_peers(self.presence_dir, "agy", tn, tt))
        if self.codex_locks_dir:
            scans.append(lambda tn, tt: load_lock_peers(self.codex_locks_dir, "codex", tn, tt))
        if self.grok_home:
            grok = _sibling("unimatrix-peer-grok.py", "unimatrix_peer_grok")
            scans.append(lambda tn, tt: grok.discover_peers(self.grok_home, _roster().pid_alive, tn, tt))
        for scan in scans:
            for peer in scan(names | set(live), targets):
                prior = owned.get(peer['target'])
                if prior and peer.get('vendor') == 'codex':
                    if peer.get('address_version') == 1 and peer['name'] != prior['name']:
                        self.log('ADDRESS-CONFLICT', peer['target'], prior['name'], peer['name'])
                        continue
                    if 'address_version' not in peer:
                        peer = {**peer, **prior}  # default refresh cannot replace an owned address
                if peer['name'] in names or peer['name'] in live:
                    self.log('ADDRESS-CONFLICT', peer['target'], peer['name'])
                    continue
                live.setdefault(peer["name"], peer)
                # Rich leg records win over the same conversation's presence lock.
                # Their cwd can produce a different display name for the same target.
                targets.add(peer["target"])
        return live

    async def refresh_discovered(self):
        """Register a face for each newly live discovered peer and retire the ones whose record or lock went."""
        await self._drop_dead_holders()
        live = await asyncio.to_thread(self._live_discovered)
        for name in sorted(self.discovered - set(live)):
            await self._retire(name)
        for name, peer in live.items():
            if name in self.peers:
                continue
            if peer["vendor"] == "codex":
                peer["tui"] = True  # a held writer lock is a TUI, so the turn goes through `codex queue`
            self.peers[name] = peer
            self.locks[name] = asyncio.Lock()
            self.discovered.add(name)
            try:
                await self._spawn_face(name)
            except Exception as e:
                self.log("DISCOVER-REGISTER-FAILED", name, type(e).__name__, e)
                await self._retire(name)

    async def _retire(self, name):
        """Drop a discovered peer: stop its face, remove its registry files and endpoint."""
        if name in self.faces:
            await self._stop_face(name)
        self.peers.pop(name, None)
        self.locks.pop(name, None)
        self.discovered.discard(name)
        self.log("retired", name)

    async def _scan_discovered(self):
        while True:
            await asyncio.sleep(LEG_SCAN_SECONDS)
            try:
                await self.check_control_socket()
                await self.refresh_discovered()
                await self._repair_faces()
            except Exception as e:
                self.log("DISCOVER-SCAN-FAILED", type(e).__name__, e)

    async def _repair_faces(self):
        """Restart each peer face whose child exited; spawn one that is missing after a failed restart."""
        for name in list(self.peers):
            if name in self.dead_holders:
                continue
            proc = self.faces.get(name)
            if proc is not None and proc.poll() is None:
                continue
            try:
                if proc is None:
                    await self._spawn_face(name)
                else:
                    await self.restart_face(name)
            except Exception as exc:
                self.log("FACE-REPAIR-FAILED", name, type(exc).__name__, exc)

    def _reconcile_orphan_faces(self):
        """Reap only locally stamped faces with matching process birth and a departed owner."""
        roster = _roster()
        try:
            paths = list(Path(self.sessions_dir).glob("*.json"))
        except OSError:
            return
        for path in paths:
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                pid, owner, name = entry.get("pid"), entry.get("unimatrixRouterPid"), entry.get("name")
                if (type(pid) is not int or type(owner) is not int or pid <= 0 or owner <= 0
                        or pid == os.getpid() or not isinstance(name, str)
                        or entry.get("sessionId") != f"peer-{name}-{pid}"
                        or entry.get("messagingSocketPath") != self.endpoint_of(name)
                        or entry.get("pidDomain") != roster.pid_domain()
                        or not entry.get("unimatrixRouterStart") or not entry.get("procStart")):
                    continue
                if roster.pid_alive(owner) and roster.proc_start(owner) == entry["unimatrixRouterStart"]:
                    continue
                if roster.pid_alive(pid):
                    if roster.proc_start(pid) != entry["procStart"]:
                        continue
                    roster.tree_kill(pid)
                sweep_pid_files(self.sessions_dir, pid)
                _unlink(self.endpoint_of(name))
                self.log("ORPHAN-FACE-REAPED", name, pid)
            except (OSError, ValueError, TypeError):
                continue

    async def _spawn_face(self, name):
        ep = self.endpoint_of(name)
        proc = _roster().spawn([_roster().console_python(), str(Path(__file__).resolve()), "face",
                                "--name", name, "--endpoint", ep, "--forward", self.ctl,
                                "--sessions-dir", self.sessions_dir,
                                "--vendor", self.peers.get(name, {}).get("vendor") or "transport",
                                "--peer-json", json.dumps(self.peers.get(name, {})),
                                "--cwd", self.peers.get(name, {}).get("cwd") or os.getcwd(),
                                "--owner-pid", str(os.getpid()),
                                "--owner-start", _roster().proc_start(os.getpid())]
                               + (["--transport"] if name in self.transport_sources else []))
        self.faces[name] = proc
        await self._wait(f"face {name}",
                         lambda p=proc: os.path.exists(os.path.join(self.sessions_dir, f"{p.pid}.json")),
                         proc)
        self.bound_faces.add(name)
        self.log("registered", name, "pid", proc.pid, ep)

    async def restart_face(self, name):
        """Replace `name`'s registration child; the new pid and key sit behind the same name and endpoint.

        Nothing supervises faces: a face that dies on its own stays dead until a caller invokes this.
        """
        await self._stop_face(name)
        await self._spawn_face(name)

    async def _stop_face(self, name):
        old = self.faces.pop(name)
        if old.poll() is None:
            old.terminate()
        try:
            await asyncio.to_thread(old.wait, 3)
        except Exception:
            _roster().tree_kill(old.pid)
            await asyncio.to_thread(old.wait, 3)
        sweep_pid_files(self.sessions_dir, old.pid)
        if name in self.bound_faces:
            _unlink(self.endpoint_of(name))
            self.bound_faces.discard(name)

    async def _bind_control(self):
        return await start_private_server(self._on_ctl, self.ctl)

    def _ctl_inode(self):
        if sys.platform == "win32":
            return None
        try:
            return os.stat(self.ctl).st_ino
        except OSError:
            return None

    async def check_control_socket(self):
        """Tick check: the control path must still be the inode this router bound; else rebind, or ask to stop."""
        if self.server is None or self.ctl_ino is None or self._ctl_inode() == self.ctl_ino:
            return
        self.log("CTL-SOCKET-LOST", self.ctl)
        try:
            self.server.close()
            self.server = None
            if os.path.exists(self.ctl) and not stat.S_ISSOCK(os.lstat(self.ctl).st_mode):
                os.unlink(self.ctl)  # the lease owns this path; only a live socket is another owner's
            self.server = await self._bind_control()
            self.ctl_ino = self._ctl_inode()
        except Exception as e:
            self.log("CTL-REBIND-FAILED", type(e).__name__, e)
            self.stop_requested.set()

    async def stop(self):
        """Remove every entry, key, endpoint, key file and child this router wrote.

        Endpoints are unlinked only when this router bound them, so a router that lost the lease or
        a face bind never removes another owner's endpoint.
        """
        if self.scanner is not None:
            self.scanner.cancel()
            self.scanner = None
        bound = self.server is not None
        if bound:
            self.server.close()
            self.server = None
        for t in list(self.tasks):
            t.cancel()
        procs = [(n, p) for n, p in self.faces.items()]
        for _, p in procs:
            if p.poll() is None:
                p.terminate()
        for _, p in procs:
            try:
                await asyncio.to_thread(p.wait, 3)
            except Exception:
                _roster().tree_kill(p.pid)  # stuck: only here is the pid still ours, not recycled
                await asyncio.to_thread(p.wait, 3)
            sweep_pid_files(self.sessions_dir, p.pid)
        for name in self.bound_faces:
            _unlink(self.endpoint_of(name))
        self.bound_faces.clear()
        self.faces = {}
        if bound:
            _unlink(self.ctl)
        if self.pid_file is not None:
            _unlink(self.pid_file)
            self.pid_file = None
        if self.lease is not None:
            _transport().unlock_file(self.lease)
            self.lease.close()
            self.lease = None

    # -- routing

    async def _on_ctl(self, reader, writer):
        try:
            line = await reader.readline()
            resp = await self._dispatch(json.loads(line)) if line.strip() else {"ok": True}
        except (ValueError, OSError) as e:
            resp = {"ok": False, "error": f"bad request: {e}"}
        try:
            writer.write((json.dumps(resp) + "\n").encode())
            await writer.drain()
        except OSError:
            pass
        finally:
            writer.close()

    async def _dispatch(self, req):
        op = req.get("op") if isinstance(req, dict) else None
        if op == "inbound":
            peer = req.get("peer")
            if not isinstance(req.get("frame"), dict):
                return {"ok": False, "error": "unknown peer or frame"}
            if peer in self.transport_sources:
                handler = self.handle_transport_inbound
            elif peer in self.peers:
                handler = self.handle_inbound
            else:
                return {"ok": False, "error": "unknown peer or frame"}
            if peer in self.peers and self.peer_stale(peer):
                return {"ok": False, "error": STALE_CODEX_ERROR}
            if peer in self.peers and self.peers[peer].get('vendor') == 'codex':
                metadata = codex_thread_metadata(self.codex_home)
                if not codex_is_sendable_root(metadata.get(self.peers[peer].get('target'), {})):
                    return {'ok': False, 'error': 'Codex target is not an independently sendable root'}
            t = asyncio.create_task(handler(peer, req["frame"]))
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)
            return {"ok": True}
        if op == "list":
            details = await asyncio.to_thread(self.session_details)
            sessions = sorted(details)
            listed = {n: p for n, p in self.peers.items() if n not in self.dead_holders}
            details.update({name: {"vendor": peer["vendor"], "box": _contract().local_box(),
                                   "cwd": peer.get("cwd") or ""}
                            for name, peer in listed.items()})
            ready = await asyncio.to_thread(self.peer_readiness)
            reachable, agents = await asyncio.to_thread(self.roster_rows, str(req.get("as") or "cli"), ready)
            return {"ok": True, "peers": sorted(listed), "reachable": reachable, "sessions": sessions,
                    "details": details, "ready": ready, "agents": agents}
        if op == "send":
            peer, text = req.get("to"), req.get("text")
            by_target = {p.get("target"): n for n, p in self.peers.items()}
            try:
                picked = self.pick_peer(peer)
            except ValueError as exc:
                picked, refusal = None, str(exc)
            else:
                refusal = None
            if picked is None and isinstance(peer, str):
                # A Codex v2 sub-agent cannot queue input; its sendable root parent receives it.
                ident = peer[len("codex-"):] if peer.startswith("codex-") else peer
                root = await asyncio.to_thread(self.codex_subagent_root, ident)
                if root == "":
                    return {"ok": False, "error": f"Codex sub-agent {ident} has no resolvable sendable root parent"}
                if root:
                    try:
                        picked = self.pick_peer(root)
                    except ValueError as exc:
                        return {"ok": False, "error": str(exc)}
                    if picked is None:
                        return {"ok": False, "error": f"root parent {root} of Codex sub-agent {ident} is not a live peer"}
            if picked is None and refusal:
                return {"ok": False, "error": refusal}
            peer = picked or peer
            # A peer's own shell knows its thread/conversation id, not the name the router gave it.
            sender = by_target.get(req.get("as_target")) or str(req.get("as") or "cli")
            reply_to = None
            as_target = req.get("as_target")
            if sender not in self.peers and isinstance(as_target, str) and as_target:
                root = await asyncio.to_thread(self.codex_subagent_root, as_target)
                if root == "":
                    return {"ok": False, "error": f"Codex sub-agent {as_target} has no resolvable sendable root parent to reply through"}
                if root:
                    reply_to = by_target.get(root) or root
                    sender = f"codex-{as_target}"
            if peer not in self.peers and isinstance(peer, str):
                if not isinstance(text, str) or is_ack(text):
                    return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
                if reply_to:
                    sender = reply_to
                if sender in self.peers:
                    return await self._peer_send_to_session(sender, peer, text)
                return await self._transport_send_to_session(sender, peer, text)
            if peer not in self.peers:
                return {"ok": False, "error": f"no peer named {peer}", "peers": sorted(self.peers)}
            if not isinstance(text, str) or is_ack(text):
                return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
            if self.peer_stale(peer):
                return {"ok": False, "error": STALE_CODEX_ERROR}
            reply = await self.turn(peer, wrap_inbound(sender, text, reply_to))
            if not_delivered(reply):
                return {"ok": False, "error": str(reply).strip()}
            return {"ok": True, "reply": _contract().label(peer, reply)}
        if op == "resolve":
            return await asyncio.to_thread(self.resolve_relay_target, req.get("name"))
        if op == "shutdown":
            # Reply first; the stop runs after the connection handler has flushed it.
            asyncio.get_running_loop().call_soon(self.stop_requested.set)
            return {"ok": True, "pid": os.getpid(), "stopping": True}
        return {"ok": False, "error": "unknown op"}

    def pick_peer(self, address):
        """Project safe legacy aliases and the native target onto one peer, never retarget."""
        if not isinstance(address, str):
            return None
        if address in self.refused_codex_addresses:
            raise ValueError('Codex target is not an independently sendable root')
        matches = [name for name, peer in self.peers.items() if address == name
                   or address == peer.get('target') or address in peer.get('aliases', [])
                   or (peer.get('vendor') == 'codex' and address == 'codex-' + peer.get('target', ''))]
        owners = {(self.peers[name]['vendor'], self.peers[name]['target']) for name in matches}
        if len(owners) > 1:
            raise ValueError(f'peer alias conflict for {address!r}')
        if address in matches:
            return address
        return next(iter(matches), None)

    def peer_readiness(self):
        """peer name -> True when a send can reach it now; an agy peer is ready only while its leg endpoint exists."""
        ready = {}
        metadata = codex_thread_metadata(self.codex_home) if any(p.get('vendor') == 'codex' for p in self.peers.values()) else {}
        for name, p in self.peers.items():
            if name in self.dead_holders:
                continue
            ok = p.get('vendor') != 'codex' or codex_is_sendable_root(metadata.get(p.get('target'), {}))
            if p.get("vendor") == "agy" and os.name != "nt":
                m = _sibling("unimatrix-peer-agy.py", "unimatrix_peer_agy_ready")
                ok = os.path.exists(m.leg_endpoint(p["target"]))
            ready[name] = ok
        return ready

    def roster_rows(self, sender="cli", ready=None):
        """(reachable names, one {name, box, vendor} row per reachable name).

        Reachable: a peer that is ready, or an external roster session whose registered endpoint
        exists; never `sender` itself. This is the set a send from `sender` can resolve now.
        """
        ready = self.peer_readiness() if ready is None else ready
        entries = {}
        try:
            files = os.listdir(self.sessions_dir)
        except FileNotFoundError:
            files = []
        for filename in files:
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.sessions_dir, filename), encoding="utf-8") as file:
                    entry = json.load(file)
            except (OSError, ValueError):
                continue
            name = entry.get("name") if isinstance(entry, dict) else None
            if (not isinstance(name, str) or name in self.peers or name in self.transport_sources
                    or entry.get("unimatrixTransport") or not isinstance(entry.get("pid"), int)
                    or not _roster().pid_alive(entry["pid"]) or not self.external_codex_sendable(entry)):
                continue
            if name in entries and (entry.get("startedAt") or 0) < (entries[name].get("startedAt") or 0):
                continue
            entries[name] = entry
        names = {name for name, ok in ready.items() if ok}
        for name, entry in entries.items():
            endpoint = entry.get("messagingSocketPath")
            if endpoint and _transport().endpoint_exists(endpoint):
                names.add(name)
        names.discard(sender)
        contract = _contract()
        box = contract.local_box()
        rows = [{"name": n, "box": box, "vendor": self.peers[n]["vendor"], "this_box": True,
                 **({"stale": True} if self.peer_stale(n) else {})} if n in self.peers
                else contract.agent_row(entries[n], box) for n in sorted(names)]
        for n, marker in sorted(self.stale_mirror_markers().items()):
            if n != sender and n not in names:
                names.add(n)
                rows.append({"name": n, "box": marker["box"], "vendor": "claude", "stale": True,
                             "this_box": marker["box"] == box})
        return sorted(names), rows

    mirror_stale_dir = os.environ.get("UNIMATRIX_LOOPBACK_SOCKS") or "/tmp/cc-socks"  # where the relay's `mirror-stale` mode writes its markers

    def stale_mirror_markers(self):
        """name -> marker for each unexpired mark a sending box left for its down mirror."""
        out = {}
        try:
            files = os.listdir(self.mirror_stale_dir)
        except OSError:
            return out
        for filename in files:
            if not filename.endswith(".stale.json"):
                continue
            try:
                with open(os.path.join(self.mirror_stale_dir, filename), encoding="utf-8") as fh:
                    m = json.load(fh)
            except (OSError, ValueError):
                continue
            if (isinstance(m, dict) and isinstance(m.get("name"), str) and isinstance(m.get("box"), str)
                    and isinstance(m.get("until"), int) and m["until"] > time.time()):
                out[m["name"]] = m
        return out

    async def turn(self, peer, text, addressed=None):
        """One adapter turn for `peer` under its lock; a failure becomes the reply text.

        `addressed`, when given, collects the names the peer sent to by its own addressed send
        during this turn, so the caller can skip the harvested reply for those.
        """
        p = self.peers[peer]
        async with self.locks[peer]:
            if addressed is not None:
                self.addressed[peer] = addressed
            try:
                if self.peer_stale(peer):
                    return f"delivery failed: {STALE_CODEX_ERROR}"
                if p["vendor"] == "codex":
                    metadata = await asyncio.to_thread(codex_thread_metadata, self.codex_home)
                    if not codex_is_sendable_root(metadata.get(p['target'], {})):
                        return 'delivery failed: Codex target is not an independently sendable root'
                if p["vendor"] == "codex" and not p.get("tui") and self.thread_held(p["target"]):
                    p = {**p, "tui": True}
                return await self.adapters[p["vendor"]](p, text)
            except Exception as e:
                self.log("TURN-FAILED", peer, type(e).__name__, e)
                return f"delivery failed: {e}"
            finally:
                if addressed is not None:
                    self.addressed.pop(peer, None)

    def thread_held(self, thread_id):
        """True while a process holds the Codex writer lock of `thread_id`, so a TUI owns the thread.

        The route follows the holder, never whether the app-server socket connects: that daemon
        is up beside a TUI and rejects a turn on a thread the TUI writes.
        """
        if not self.codex_locks_dir or not thread_id:
            return False
        return lock_held(os.path.join(self.codex_locks_dir, f"{thread_id}.lock"))

    def _session_at(self, endpoint):
        """True when a roster session file registers `endpoint` as its messaging socket."""
        try:
            files = os.listdir(self.sessions_dir)
        except FileNotFoundError:
            return False
        for f in files:
            try:
                with open(os.path.join(self.sessions_dir, f), encoding="utf-8") as fh:
                    e = json.load(fh)
            except (OSError, ValueError):
                continue
            if endpoint and isinstance(e, dict) and e.get("messagingSocketPath") == endpoint:
                return True
        return False

    def session_names(self):
        """Names of the live roster sessions that are not the router's own peers."""
        names = set()
        try:
            files = os.listdir(self.sessions_dir)
        except FileNotFoundError:
            return []
        for f in files:
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.sessions_dir, f), encoding="utf-8") as fh:
                    e = json.load(fh)
            except (OSError, ValueError):
                continue
            if (isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"] not in self.peers and e["name"] not in self.transport_sources
                    and isinstance(e.get("pid"), int) and _roster().pid_alive(e["pid"]) and self.external_codex_sendable(e)):
                names.add(e["name"])
        return sorted(names)

    def session_details(self):
        """Identity metadata for external sessions, keyed by their unchanged routable names."""
        details, latest = {}, {}
        try:
            files = os.listdir(self.sessions_dir)
        except FileNotFoundError:
            return details
        for filename in files:
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.sessions_dir, filename), encoding="utf-8") as file:
                    entry = json.load(file)
            except (OSError, ValueError):
                continue
            if not isinstance(entry, dict):
                continue
            name, pid = entry.get("name"), entry.get("pid")
            if (not isinstance(name, str) or name in self.peers or name in self.transport_sources
                    or entry.get("unimatrixTransport") or not isinstance(pid, int)
                    or not _roster().pid_alive(pid) or not self.external_codex_sendable(entry)):
                continue
            rank = entry.get("startedAt") or 0
            if name in latest and latest[name] > rank:
                continue
            latest[name] = rank
            details[name] = {**_roster().session_identity(entry), "status": entry.get("status") or "unknown"}
        return details

    async def _transport_face(self, source, destination):
        """Lazily register a genuine transport sender for one source/destination conversation."""
        name = readable_peer_name("unimatrix", source + "\0" + destination, "transport")
        async with self.transport_lock:
            self.transport_sources[name] = source if self.resolve_sender(source) else None
            self.transport_targets[name] = destination
            process = self.faces.get(name)
            if process is not None and process.poll() is not None:
                await self._stop_face(name)
                process = None
            if process is None:
                try:
                    await self._spawn_face(name)
                except BaseException:
                    self.transport_sources.pop(name, None)
                    self.transport_targets.pop(name, None)
                    raise
        return name

    def resolve_relay_target(self, name):
        """Strict relay target for the live local session called `name`; the answer an inbound relay delivers by.

        {"ok": True, "endpoint", "name", "box"} for exactly one live session. Otherwise a refusal
        that is logged either way (RELAY-TARGET / RELAY-REFUSED); an unknown or ambiguous name is
        never mapped to another session or a default inbox.
        """
        endpoint = self.resolve_sender(name) if isinstance(name, str) and name else ""
        if not endpoint:
            reason = self.last_refusal or "no live session"
            self.log("RELAY-REFUSED", name, reason)
            return {"ok": False, "error": f"no unique live session named {name}: {reason}", "recorded": True}
        row = self.last_resolved_row or (name, "")
        self.log("RELAY-TARGET", name, "->", row[0], row[1])
        return {"ok": True, "endpoint": endpoint, "name": row[0], "box": row[1]}

    def _session_rows(self):
        """Every readable session entry in the registry, listed or not."""
        rows = []
        try:
            files = os.listdir(self.sessions_dir)
        except OSError:
            return rows
        for f in files:
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.sessions_dir, f), encoding="utf-8") as fh:
                    row = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def resolve_send_target(self, name):
        """{"ok": True, "endpoint", "name", "box"} when `name` is a session the roster listing shows, else
        {"ok": False, "error"} naming it. A ghost or unknown name never reaches a bridge."""
        endpoint = self.resolve_sender(name) if isinstance(name, str) and name else ""
        if endpoint:
            rows = self._session_rows()
            held = [r for r in rows if r.get("messagingSocketPath") == endpoint]
            if not any(_roster().listed_row(r, rows) for r in held):
                endpoint = ""
                self.last_refusal = "not in the live listing"
        if not endpoint:
            self.last_resolved_far, self.last_resolved_row = False, None
            return {"ok": False, "error": f"no unique live session named {name}" + self._refusal_suffix()}
        row = self.last_resolved_row or (name, "")
        return {"ok": True, "endpoint": endpoint, "name": row[0], "box": row[1]}

    def _refusal_suffix(self):
        return f" ({self.last_refusal})" if self.last_refusal else ""

    def relay_route(self, endpoint, to):
        """(endpoint, error): where a frame for the session at `endpoint` may be written on this box.

        A pipe address is never opened off Windows; the frame goes to a live local mirror row carrying
        the same far session id (its bridge relays by session id), else the send is refused."""
        if not _off_windows() or not _transport().is_pipe(endpoint):
            return endpoint, ""
        rows = []
        try:
            for f in os.listdir(self.sessions_dir):
                if f.endswith(".json"):
                    with open(os.path.join(self.sessions_dir, f), encoding="utf-8") as fh:
                        rows.append(json.load(fh))
        except (OSError, ValueError):
            pass
        rows = [r for r in rows if isinstance(r, dict)]
        sid = next((r.get("sessionId") for r in rows if r.get("messagingSocketPath") == endpoint), None)
        for r in rows:
            ep, pid = r.get("messagingSocketPath"), r.get("pid")
            if (sid and r.get("sessionId") == sid and r.get("unimatrixRemote") and ep and not _transport().is_pipe(ep)
                    and isinstance(pid, int) and _roster().pid_alive(pid)):
                return ep, ""
        return "", f"{to} is a Windows pipe endpoint and this box has no relay route to it"

    async def _transport_send_to_session(self, source, to, text):
        target = self.resolve_send_target(to)
        endpoint = target.get("endpoint", "")
        if not endpoint:
            self.log("RELAY-REFUSED", to, self.last_refusal or "no live session")
            return {**target, "peers": sorted(self.peers)}
        far, reached = self.last_resolved_far, self.last_resolved_row
        endpoint, refusal = self.relay_route(endpoint, to)
        if refusal:
            return {"ok": False, "error": refusal}
        try:
            transport = await self._transport_face(source, to)
            content = f"[{source} via Unimatrix transport] {text}"
            box = _contract().local_box()
            frame = _contract().build_frame(self.endpoint_of(transport), transport, content, from_box=box)
            if far:
                frame = routable_from(frame, f"{source}.{box}")
            frame = _contract().stamp(frame, transport, "transport", source, os.getpid(), from_box=box)
            await self._deliver_as_peer(transport, endpoint, frame)
        except Exception as exc:
            return {"ok": False, "error": f"transport delivery to {to} failed: {exc}"}
        self.log("SENT-TRANSPORT", source, "->", to, frame["msg_id"])
        return {"ok": True, "msg_id": frame["msg_id"], "sender": transport, "written": True, **_receipt(reached)}

    def _is_face_target(self, transport, sender, sender_endpoint):
        """True when the frame comes from the session the face was opened to reach."""
        target = self.transport_targets.get(transport)
        target_endpoint = self.resolve_sender(target) if target else ""
        return bool(target_endpoint and sender_endpoint == target_endpoint) if sender_endpoint else sender == target

    def _holds_receiver(self, session_name, receiver):
        """True when the session called `session_name` is `receiver` by name or role.

        A slot-admission receiver resolves by role to the roster's group-em session on any box."""
        wanted = SLOT_ROLE if receiver in SLOT_RECEIVERS else receiver
        return _contract().holds_receiver(session_name, wanted)

    async def handle_transport_inbound(self, transport, frame):
        """Bridge both reply directions without pretending to be either endpoint's vendor."""
        source = self.transport_sources.get(transport)
        if not source:
            self.log("NO-TRANSPORT-RETURN", transport)
            return
        sender_endpoint, sender, body = _contract().parse_inbound(frame)
        if is_ack(body):
            return
        if hop_count(body) >= TRANSPORT_HOP_LIMIT:
            self.log("TRANSPORT-LOOP-DROPPED", transport, sender, hop_count(body))
            return
        source_endpoint = self.resolve_sender(source)
        from_source = bool(source_endpoint and sender_endpoint == source_endpoint) if sender_endpoint else sender == source
        destination = self.transport_targets[transport] if from_source else source
        endpoint = self.resolve_sender(destination)
        resolved_row = self.last_resolved_row
        reflected = (endpoint == sender_endpoint if self._session_at(sender_endpoint)
                     else destination == sender)
        if reflected or destination in hop_chain(body):
            self.log("TRANSPORT-LOOP-DROPPED", transport, sender, "self" if reflected else "chain")
            return
        if not endpoint:
            self.log("NO-TRANSPORT-RETURN", transport)
            return
        receiver = _contract().intended_receiver(frame)
        if not from_source and not receiver and not self._is_face_target(transport, sender, sender_endpoint):
            self.log("TRANSPORT-RECEIVER-REFUSED", transport, sender, "->", destination, "names no intended receiver")
            return
        receiver = receiver or destination
        held = resolved_row[0] if resolved_row else destination
        if not self._holds_receiver(held, receiver):
            self.log("TRANSPORT-RECEIVER-REFUSED", transport, sender, "->", held, "intended", receiver)
            return
        box = _contract().local_box()
        outgoing = _contract().build_frame(self.endpoint_of(transport), transport,
                                          f"[forwarded message from {sender}] {body}", from_box=box,
                                          to_name=receiver)
        outgoing = _contract().stamp(outgoing, transport, "transport", source, os.getpid(), from_box=box)
        try:
            await self._deliver_as_peer(transport, endpoint, outgoing)
        except Exception as exc:
            self.log("TRANSPORT-RETURN-FAILED", transport, type(exc).__name__)

    async def _deliver_as_peer(self, peer, endpoint, frame):
        """Send through the registered face so the OS client PID matches frame.from."""
        response = await asyncio.to_thread(request_line, self.endpoint_of(peer),
            {"op": "deliver", "endpoint": endpoint, "frame": frame}, 15)
        if not response.get("ok"):
            raise OSError(response.get("error", "face delivery failed"))

    async def _peer_send_to_session(self, peer, to, text):
        """A peer's own addressed send to a Claude session `to`; marks the peer's open turn as answered."""
        target = self.resolve_send_target(to)
        ep = target.get("endpoint", "")
        if not ep:
            self.log("RELAY-REFUSED", to, self.last_refusal or "no live session")
            return {**target, "peers": sorted(self.peers)}
        far, reached = self.last_resolved_far, self.last_resolved_row
        ep, refusal = self.relay_route(ep, to)
        if refusal:
            return {"ok": False, "error": refusal}
        p = self.peers[peer]
        box = _contract().local_box()
        frame = _contract().build_frame(self.endpoint_of(peer), peer, _contract().label(peer, text), from_box=box)
        if far:
            frame = routable_from(frame, f"{peer}.{box}")
        frame = _contract().stamp(frame, peer, p["vendor"], p["target"], os.getpid(), from_box=box)
        try:
            await self._deliver_as_peer(peer, ep, frame)
        except Exception as e:
            self.log("POST-FAILED", peer, "->", to, type(e).__name__, e)
            return {"ok": False, "error": f"delivery to {to} failed: {e}"}
        if peer in self.addressed:
            self.addressed[peer].add(to)
        self.log("SENT", peer, "->", to, frame["msg_id"])
        return {"ok": True, "msg_id": frame["msg_id"], "written": True, **_receipt(reached)}

    def external_codex_sendable(self, entry):
        """Gate resolved roster identity, never infer native UUID from a face/name/PID.

        Remote mirrors carry a live local bridge generation plus explicit far
        socket/box fields. Their native source belongs to that box, not our DB.
        """
        roster = _roster()
        if roster.session_identity(entry).get('vendor') != 'codex':
            return True
        remote_fields = ('unimatrixRemote', 'macSocketPath', 'unimatrixMirror')
        if any(entry.get(key) for key in remote_fields):
            remote, far_socket, box = (entry.get('unimatrixRemote'), entry.get('macSocketPath'), entry.get('box'))
            pid, far_pid = entry.get('pid'), entry.get('farPid')
            if not (isinstance(remote, str) and remote.strip() and isinstance(far_socket, str) and far_socket
                    and isinstance(box, str) and box.strip() and _contract().box_id(box) != _contract().local_box()
                    and type(pid) is int and pid > 0 and type(far_pid) is int and far_pid > 0):
                return False
            try:
                return (roster.pid_alive(pid) and entry.get('procStart') is not None
                        and entry['procStart'] == roster.proc_start(pid)
                        and entry.get('pidDomain') == roster.pid_domain())
            except (OSError, ValueError, TypeError):
                return False
        target, session_id = entry.get('target'), entry.get('session_id')
        if target is not None and session_id is not None and target != session_id:
            return False
        target = target if target is not None else session_id
        if not isinstance(target, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', target):
            return False
        return codex_is_sendable_root(codex_thread_metadata(self.codex_home).get(target, {}))

    def codex_subagent_root(self, ident):
        """None when `ident` is not a known Codex sub-agent; else its sendable root thread id, or "" if unresolvable."""
        if not isinstance(ident, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', ident):
            return None  # a session name is no thread id: skip the sqlite read and rollout scan
        metadata, rollouts = codex_thread_metadata(self.codex_home), []

        def lookup(thread):
            row = dict(metadata.get(thread) or {})
            if not row or (codex_is_subagent(row) and not codex_parent_id(row)):
                extra = codex_rollout_identity(self.codex_home, thread, rollouts)
                if not row or codex_parent_id(extra):
                    row = {**row, **extra}
            return row
        if not codex_is_subagent(lookup(ident)):
            return None
        return codex_root_parent(ident, lookup) or ""

    def resolve_sender(self, name, fallback=""):
        """Current messaging endpoint of the live roster session called `name`, else `fallback`.

        Re-read on every reply, so a sender that restarted under a new pid/endpoint keeps its
        name as its address. The router's own faces never match a Claude sender.
        """
        exact, aliases, owners, far_eps = set(), set(), set(), set()
        rows_by_ep, ep_owners = {}, {}
        owned_alias = False
        refused_identity = False
        self.last_refusal, self.last_resolved_far, self.last_resolved_row = "", False, None
        try:
            names = os.listdir(self.sessions_dir)
        except FileNotFoundError:
            return fallback
        for f in names:
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.sessions_dir, f), encoding="utf-8") as fh:
                    e = json.load(fh)
            except (OSError, ValueError):
                continue
            if (not isinstance(e, dict) or name not in [e.get("name"), e.get("unimatrixFarName"), *_contract().projected_addresses(e)]
                    or name in self.peers or name in self.transport_sources):
                continue
            ep, pid = e.get("messagingSocketPath"), e.get("pid")
            if not ep or not isinstance(pid, int) or not _roster().pid_alive(pid):
                continue
            if not self.external_codex_sendable(e):
                refused_identity = True
                continue
            if _far_alias_is_stale(e) or _ref_contradicts_session(e, name):
                refused_identity = True
                continue
            owned_alias = owned_alias or name in _contract().projected_addresses(e)
            owner = (e.get('vendor'), e.get('target') or e.get('sessionId') or ep)
            owners.add(owner)
            ep_owners.setdefault(ep, set()).add(owner)
            (exact if e.get("name") == name else aliases).add(ep)
            rows_by_ep[ep] = e
            if e.get("unimatrixFarName") or e.get("unimatrixRemote"):
                far_eps.add(ep)
        if refused_identity:
            self.last_refusal = "refused identity"
            return ''  # Never retarget a refused local identity to another matching row/fallback.
        if owned_alias and len(owners) > 1:
            self.last_refusal = "ambiguous: owned alias collides with another target"
            return ''  # A projected alias cannot override another target's exact name.
        if any(len(o) > 1 for o in ep_owners.values()):
            self.last_refusal = "ambiguous: one endpoint carries several sessions"
            return ""  # An endpoint is not an identity: rows with different sessions on it never resolve.
        matches = exact | aliases
        if len(matches) > 1:
            self.last_refusal = f"ambiguous: {len(matches)} live sessions carry this name"
            return ""  # An exact name never beats a far alias: both are live carriers of the address.
        self.last_resolved_far = bool(matches) and matches <= far_eps
        if matches:
            row = rows_by_ep[next(iter(matches))]
            self.last_resolved_row = (row.get("name"), _contract().agent_row(row, _contract().local_box())["box"])
            return next(iter(matches))
        return fallback

    async def handle_inbound(self, peer, frame):
        sender_ep, sender_name, body = _contract().parse_inbound(frame)
        if is_ack(body) or body.lstrip().lower().startswith("[reply]"):
            self.log("DROPPED-ACK", sender_name, "->", peer)
            return
        addressed = set()
        reply = await self.turn(peer, wrap_inbound(sender_name, body), addressed)
        if not sender_ep:
            return
        if sender_name in addressed:
            self.log("DEDUP-ADDRESSED", peer, "->", sender_name)
            return
        if not str(reply or "").strip():
            self.log("DROPPED-EMPTY-REPLY", peer, "->", sender_name)
            return
        if str(reply).strip() in NO_REPLY_MARKERS:  # the peer is still busy (an approval prompt, say), not answering
            self.log("NO-REPLY-YET", peer, "->", sender_name)
            return
        if sender_ep in self.peer_endpoints() or sender_name in self.peers:
            self.log("NO-REPLY-TO-PEER", peer, "->", sender_name)
            return
        resolved = self.resolve_sender(sender_name, sender_ep)
        if not resolved:
            self.log("NO-REPLY-UNRESOLVED", peer, "->", sender_name, self.last_refusal)
            return
        far = self.last_resolved_far
        if resolved != sender_ep and not far:
            self.log("REPLY-KEEPS-FRAME-ENDPOINT", peer, "->", sender_name)  # a local row sharing a far sender's name is not that sender
        else:
            sender_ep = resolved
        p = self.peers[peer]
        box = _contract().local_box()
        frame = _contract().build_frame(self.endpoint_of(peer), peer, f"[reply] {peer}: {str(reply).strip()}",
                                        from_box=box)
        if far:
            frame = routable_from(frame, f"{peer}.{box}")
        frame = _contract().stamp(frame, peer, p["vendor"], p["target"], os.getpid(), from_box=box)
        try:
            await self._deliver_as_peer(peer, sender_ep, frame)
        except Exception as e:
            self.log("POST-FAILED", peer, "->", sender_name, type(e).__name__, e)
            return
        resp = {"ok": True, "msg_id": frame["msg_id"]}
        self.log("REPLIED", peer, "->", sender_name, resp)


def _off_windows():
    return os.name != "nt"


def deliver(endpoint, data, sessions_dir=None):
    """Write an authenticated frame to a registered session's Unix socket or Windows pipe."""
    data = _roster().authenticated_data(endpoint, data, sessions_dir)
    if _transport().is_pipe(endpoint):
        _check_delivery_reply(_transport().pipe_exchange(endpoint, data, 10, ACCEPT_READ_SECONDS))
        return
    s = socket.socket(socket.AF_UNIX)
    try:
        s.settimeout(10)
        s.connect(endpoint)
        s.sendall(data)
        try:
            s.shutdown(socket.SHUT_WR)
        except OSError as exc:
            if exc.errno != errno.ENOTCONN:
                raise
        s.settimeout(ACCEPT_READ_SECONDS)
        try:
            reply = s.recv(4096)
        except socket.timeout:
            reply = b""
        _check_delivery_reply(reply)
    finally:
        s.close()


def _check_delivery_reply(reply):
    """Silence is acceptance (the harness writes no reply line); any line other than {"ok": true} raises."""
    line = reply.split(b"\n", 1)[0].strip()
    if not line:
        return
    try:
        if json.loads(line).get("ok") is True:
            return
    except (ValueError, AttributeError):
        pass
    raise RuntimeError(f"refused: {line.decode('utf-8', 'replace')[:200]}")


def _unlink(path):
    if str(path).startswith("\\\\.\\pipe\\"):
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


async def serve(router):
    await router.start()
    _transport().install_stop_handlers(router.stop_requested)
    try:
        await router.stop_requested.wait()
    finally:
        await router.stop()


def cmd_send(argv):
    p = argparse.ArgumentParser(prog="unimatrix-peer-router.py send")
    p.add_argument("--as", dest="as_name", default=os.environ.get("UNIMATRIX_PEER_NAME", "cli"))
    p.add_argument("--endpoint-dir", default=None)
    p.add_argument("peer")
    p.add_argument("text", nargs="+")
    a = p.parse_args(argv)
    ctl = endpoint_path(ROUTER_ENDPOINT_SEED, a.endpoint_dir)
    try:
        resp = request_line(ctl, {"op": "send", "as": a.as_name, "to": a.peer, "text": " ".join(a.text)})
    except PermissionError as e:
        print(f"connect to router socket {ctl} denied by the caller's sandbox, not a router fault: {e}; "
              "allow the socket path or run the send unsandboxed", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"router not reachable at {ctl}: {e}", file=sys.stderr)
        return 1
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        if resp.get("peers"):
            print("peers: " + ", ".join(resp["peers"]), file=sys.stderr)
        return 1
    if "reply" in resp:
        print(resp["reply"])
        return 0
    delivered = ", ".join(f"{k}={resp[k]}" for k in ("msg_id", "sender") if k in resp)
    print(f"delivered to {a.peer}" + (f" ({delivered})" if delivered else "") + "; the router returned no reply field")
    print("router-version mismatch: the running router answers with an older or different send reply shape; "
          "restart the router (stop the running unimatrix-peer-router.py and start it again)", file=sys.stderr)
    return 0


def cmd_face(argv):
    p = argparse.ArgumentParser(prog="unimatrix-peer-router.py face")
    p.add_argument("--name", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--forward", required=True)
    p.add_argument("--sessions-dir", required=True)
    p.add_argument("--cwd", default=None)
    p.add_argument("--transport", action="store_true")
    p.add_argument("--vendor", default=None)
    p.add_argument("--peer-json", default='{}')
    p.add_argument("--owner-pid", type=int, default=None)
    p.add_argument("--owner-start", default=None)
    a = p.parse_args(argv)
    asyncio.run(run_face(a.name, a.endpoint, a.forward, a.sessions_dir, a.cwd, a.transport, a.vendor,
                         json.loads(a.peer_json), a.owner_pid, a.owner_start))
    return 0


def cmd_serve(argv):
    p = argparse.ArgumentParser(prog="unimatrix-peer-router.py")
    p.add_argument("--peers", default=None, help="peers.json (default: <settings home>/unimatrix/peers.json)")
    p.add_argument("--sessions-dir", default=None)
    p.add_argument("--state-dir", default=None)
    p.add_argument("--endpoint-dir", default=None)
    a = p.parse_args(argv)
    peers_file = a.peers or default_peers_file()
    try:
        peers = _contract().load_peers(peers_file)
    except FileNotFoundError:
        peers = []  # discovery alone can supply peers
    except (OSError, ValueError, _contract().PeerConfigError) as e:
        print(f"cannot read peers from {peers_file}: {e}", file=sys.stderr)
        return 2
    asyncio.run(serve(Router(peers, a.sessions_dir, a.state_dir, a.endpoint_dir,
                             legs_dir=default_legs_dir(), codex_locks_dir=default_codex_locks_dir(),
                             presence_dir=default_presence_dir(),
                             grok_home=_sibling("unimatrix-peer-grok.py", "unimatrix_peer_grok").grok_home())))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "face":
        return cmd_face(argv[1:])
    if argv and argv[0] == "send":
        return cmd_send(argv[1:])
    return cmd_serve(argv)


if __name__ == "__main__":
    sys.exit(main())
