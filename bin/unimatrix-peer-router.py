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
  unimatrix-peer-router.py --restart [--from SRC_DIR] [--dest DIR]
      Refresh the installed scripts from SRC_DIR (default: this script's directory, which must hold
      unimatrix-install.py), then drain and replace the running router on the refreshed code.

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
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import socket
import stat
import sys
import threading
import time
import uuid
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


def _drain_queued_sessions() -> list:
    """Run the relay's local `drain` for each session with a non-empty queue file; returns `(session, error)` pairs.

    The relay is loaded in-process by path (no process per session); one session's failure never skips the next."""
    relay = _sibling("unimatrix-relay.py", "unimatrix_relay")
    get_queue = getattr(relay, "_relay_queue", None)
    queue = get_queue() if callable(get_queue) else None
    if queue is None:
        return []
    failures = []
    for path in sorted(queue.queue_dir().glob("*.jsonl")):
        try:
            if path.stat().st_size == 0:
                continue
            relay.drain(path.stem)  # {"ok": False} (no unique live local session): the lines stay queued
        except Exception as e:
            failures.append((path.stem, f"{type(e).__name__}: {e}"))
    return failures


def _roster():
    """The unimatrix-roster module, loaded on first use."""
    return _sibling("unimatrix-roster.py", "unimatrix_roster")


def _core_module(subname):
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and os.path.isdir(os.path.join(bin_dir, "_unimatrix")):
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
    import importlib
    return importlib.import_module(f"_unimatrix.{subname}")


def _liveness():
    """The liveness module (codex_holder_live), loaded on first use."""
    return _core_module("proc")


def _contract():
    """The peer contract module, loaded on first use."""
    return _core_module("protocol")


def _box_id_aliases(row) -> list:
    """Every `<stem>.<box alias>` that names a far mirror: the box id (`<name>.machine-a`), its `-lan` and
    `.local` forms and the host spelled in the row's box fields (`.Machine-b.local`), so each roster alias
    reaches the session the listing shows. Empty for a row with no far markers or box."""
    if not isinstance(row, dict) or not any(row.get(k) for k in ("unimatrixRemote", "macSocketPath", "unimatrixBox", "unimatrixFarName")):
        return []
    own = row.get("name")
    if not isinstance(own, str) or "." not in own:
        return []
    stem = own.partition(".")[0]
    far = row.get("unimatrixFarName")
    stems = {stem, *([far.partition(".")[0]] if isinstance(far, str) and far else [])}
    boxes = set()
    for key in ("unimatrixBox", "box", "unimatrixRemote"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            boxid = _contract().box_id(value)
            if boxid and not _contract().is_ip_literal(boxid):
                host = value.strip().rpartition("@")[2]
                boxes |= {boxid, f"{boxid}-lan", f"{boxid}.local", host, host.partition(".")[0]}
    return [f"{s}.{b}" for s in sorted(stems) for b in sorted(boxes) if b]


def _transport():
    """The local transport module (sockets, named pipes, process locks), loaded on first use."""
    return _core_module("transport")


def __getattr__(name):
    if name == "PipeServer":
        return _transport().PipeServer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_ROUTER_NAME = "unimatrix-peer-router.py"
_SCRIPT_REF = r"unimatrix-[a-z0-9-]+\.py"  # a pattern string, not compiled: import must compile nothing (peer contract)
DRAIN_SECONDS = 30


def code_digest(root=None) -> str:
    """sha256 over the router's script closure and lib/*.py in `root`, the same bytes the installer digests.

    Recorded in router.pid.json at start so an installer can tell a router started on older code from the
    installed copy. Mirrors unimatrix-install.py router_closure_digest."""
    root = Path(root) if root else here()
    seen, todo = set(), [_ROUTER_NAME]
    while todo:
        name = todo.pop()
        if name in seen or name == "unimatrix-install.py":
            continue
        seen.add(name)
        path = root / name
        if path.is_file():
            todo.extend(re.findall(_SCRIPT_REF, path.read_text(encoding="utf-8")))
    names = sorted(seen) + [f"lib/{p.name}" for p in sorted((root / "lib").glob("*.py"))]
    names += sorted(p.relative_to(root).as_posix() for p in (root / "_unimatrix").rglob("*.py") if "__pycache__" not in p.parts)
    h = hashlib.sha256()
    for name in sorted(names):
        try:
            data = (root / name).read_bytes()
        except OSError:
            continue
        h.update(name.encode("utf-8") + b"\0" + data + b"\0")
    return h.hexdigest()


def default_peers_file():
    """The peers file a default invocation reads."""
    return _roster().delivery_settings_home() / "unimatrix" / "peers.json"


def default_legs_dir():
    """Where the agy launch hook writes one leg record per conversation."""
    return _roster().delivery_settings_home() / "unimatrix" / "agy-legs"


def leg_record_live(rec) -> bool:
    """True only when the record's leg pid is alive and still the process that stamped `procStart`.

    A record with no procStart is not shown live: a recycled pid must never revive a dead leg.
    A `mode` other than live (a pending leg only spools) is not live either; an absent mode reads live.
    """
    try:
        return rec.get("mode", "live") == "live" and _leg_process_matches(rec)
    except AttributeError:
        return False


def _leg_process_matches(rec) -> bool:
    """True when the record's pid is alive and still the process that stamped `procStart`; mode is not read."""
    try:
        pid, stamp = int(rec["pid"]), rec.get("procStart")
        return stamp is not None and _roster().pid_alive(pid) and _roster().proc_start(pid) == stamp
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def leg_target_live(legs_dir, target):
    """True when `legs_dir` holds a live leg record for `target` whose agy session does not read dead.

    Same two gates as `load_leg_peers`: an orphaned leg whose agy app is gone is not live, or
    `_repair_faces` respawns a face the reaper keeps reaping.
    """
    try:
        with open(os.path.join(legs_dir, f"{target}.json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        return leg_record_live(rec) and _liveness().agy_session_state(target, rec) != "dead"
    except (OSError, ValueError, TypeError):
        return False


def load_leg_peers(legs_dir, taken_names=(), taken_targets=(), pending_out=None) -> list:
    """Peers for every live agy leg record in `legs_dir`: name agy-<conversation>, target the conversation.

    A record whose leg is not live (`leg_record_live`), whose agy session reads dead
    (`agy_session_state`: a leaked leg must not revive its face), whose name or conversation is
    already `taken_*` (peers.json wins), or that is unreadable is skipped.
    A `mode: pending` leg with a matching live process is never returned; when `pending_out` is a
    dict it gains name -> peer for each (the leg only spools, so it is listed pending, never ready).
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
        if not isinstance(conv, str) or not conv or conv in taken_targets:
            continue
        live = leg_record_live(rec)
        pending = not live and pending_out is not None and rec.get("mode") == "pending" and _leg_process_matches(rec)
        if not live and not pending:
            continue
        if _liveness().agy_session_state(conv, rec) == "dead":
            continue
        name = readable_peer_name("agy", conv, rec.get("cwd"))
        if name in taken_names:
            continue
        peer = {"name": name, "vendor": "agy", "target": conv}
        if rec.get("cwd") and not under_agy_config_home(rec["cwd"]):
            peer["cwd"] = rec["cwd"]
        if pending:
            pending_out[name] = peer
        else:
            peers.append(peer)
    return peers


def default_codex_locks_dir():
    """Where Codex keeps one writer lock per live thread: $CODEX_HOME (else ~/.codex)/thread-writer-locks."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "thread-writer-locks"


def default_presence_dir() -> Path:
    """Where agy keeps one presence lock per live conversation: next to its brain root (AGY_BRAIN_DIR)."""
    return _liveness().agy_presence_dir()


def under_agy_config_home(path) -> bool:
    """True when `path` is the agy config home (~/.gemini) or inside it: agy runs hooks there, so it is no launch dir."""
    try:
        home = os.path.normcase(os.path.abspath(Path.home() / ".gemini"))
        target = os.path.normcase(os.path.abspath(os.fsdecode(path)))
        return target == home or target.startswith(home + os.sep)
    except (OSError, ValueError, TypeError, RuntimeError):
        return False


def readable_peer_name(vendor, target, cwd=None) -> str:
    """Stable routing name carrying vendor, repository, session identity and box.

    An agy cwd under the agy config home is no launch dir: it names the face as if no cwd were known.
    """
    cwd = os.fsdecode(cwd) if isinstance(cwd, (str, os.PathLike)) else ""
    if vendor == "agy" and cwd and under_agy_config_home(cwd):
        cwd = ""
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


def lock_held(path) -> bool:
    """True while another process holds the lock on `<id>.lock`; a free or unreadable file is not live.

    Delegates to liveness's `agy_presence_held` (one probe): exclusive-probe, so a shared-mode holder
    reads as held; a missing file, an unsafe id or a non-contention lock error reads as not held.
    """
    path = Path(path)
    if not path.name.endswith(".lock"):
        return False
    return _liveness().agy_presence_held(path.name[:-len(".lock")], presence_dir=path.parent)


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
                    _roster().delivery_settings_home() / 'host-sessions' / 'codex', ident, socket.gethostname())
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
HELD_REPLY = "[unimatrix-router] held behind an unechoed Codex item"
STRANDED_REPLY = "[unimatrix-peer-codex] queued item stranded"  # unimatrix-peer-codex.py STRANDED
NOT_DELIVERED_PREFIXES = ("[unimatrix-peer-agy] not delivered", "[unimatrix-peer-agy] delivery failed",
                          "delivery failed:")


_MIRROR_MARKERS = ("unimatrixRemote", "macSocketPath", "unimatrixMirror", "farPid")


def _push_only_mirror(entry) -> bool:
    """True for a relay-pushed mirror row: a socket forwarding onto the far relay's push channel, no bridge behind it."""
    return bool(entry.get("unimatrixMirror")) and not (entry.get("unimatrixRemote") or entry.get("macSocketPath"))


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


def wrap_inbound(sender, body, reply_to=None) -> str:
    """What a peer sees: `[<sender>] <body>` plus a trailer naming the sender and the exact reply command.

    `reply_to` overrides the --to address when the sender itself cannot be queued (a Codex v2 sub-agent).
    """
    if sender == "cli" and not reply_to:
        return f"[cli] {body}\n\nNo verified reply address; ask the sender to use native SendMessage."
    # Run through the interpreter, never the exec bit: Windows has none (check_posix_exec_assumptions).
    if sys.platform == "win32":
        # PowerShell call-operator form; a peer driving a POSIX shell on Windows cannot run it.
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        # Paths may carry spaces and are always quoted; a PowerShell-safe address stays bare, as shlex.quote leaves it.
        quote_address = lambda value: (
            str(value) if re.fullmatch(r"[A-Za-z0-9_.:/][A-Za-z0-9_.:/-]*", str(value)) else quote(value))
        send = f"& {quote(sys.executable)} {quote(here() / SEND_SCRIPT)}"
    else:
        quote = quote_address = shlex.quote
        send = f"{quote(sys.executable)} {quote(str(here() / SEND_SCRIPT))}"
    return (f"[{sender}] {body}\n\nFrom agent {sender}, not the PM. "
            f"Never answer them in plain text to the human at your keyboard. "
            f"Reply to them with: {send} --to {quote_address(str(reply_to or sender))} '<your reply>'")


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
    return _roster().delivery_settings_home() / "unimatrix" / "router"


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


def request_line(endpoint, request, timeout=SEND_TIMEOUT, prefix=b"") -> dict:
    """Send one JSON line (after optional raw `prefix` lines, e.g. an auth frame) and return the one-line JSON answer."""
    payload = prefix + (json.dumps(request) + "\n").encode("utf-8")
    if _transport().is_pipe(endpoint):
        raw = _transport().pipe_exchange(endpoint, payload, timeout)
        return json.loads(raw.split(b"\n", 1)[0] or b'{"ok":false,"error":"closed"}')
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    try:
        s.connect(endpoint)
        s.sendall(payload)
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


def _no_pause() -> None:
    """Default for ROTATE_PAUSE_HOOK."""


# Called between "face accepted {old,new}" and "key file replaced"; tests swap it to pause there.
ROTATE_PAUSE_HOOK = _no_pause

MAX_GRACE_S = 3600


class Registration:
    """A registry entry plus its 0600 key file for one endpoint, keyed by the writing pid."""

    def __init__(self, name, endpoint, sessions_dir, cwd=None, vendor=None, peer=None, leg_mode=None) -> None:
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
        self._previous = (None, 0.0)  # (old token, monotonic deadline)
        self._rotate_lock = threading.Lock()
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
        if leg_mode:
            self.data["leg_mode"] = leg_mode
        if native_target is not None:
            # Explicit router-owned binding, also for legacy display names.
            # Do not invent an engine-owned alias, role or parent identity.
            self.data['target'] = native_target
        if isinstance(peer, dict) and 'address_version' in peer:
            address = _contract().owned_codex_address(peer, peer.get('target'))
            if vendor != 'codex' or address['name'] != name:
                raise _contract().PeerConfigError('face does not match engine-owned Codex address')
            self.data.update(address, target=peer['target'], aliases=list(peer.get('aliases', [])), nameSource='engine')

    def _key_data(self) -> dict:
        return {"peerToken": self.token, ("procStartFt" if sys.platform == "win32" else "procStart"): self.data["procStart"],
                "pidDomain": self.data["pidDomain"]}

    def write(self) -> None:
        _private_dir(self.sessions_dir)
        _roster().write_peer_key(self.key, self._key_data())
        _roster().write_json_atomic(self.entry, self.data)

    def accepts(self, token) -> bool:
        """True for the current token, or the previous one until its monotonic grace deadline."""
        if not isinstance(token, str):
            return False
        if secrets.compare_digest(token.encode("utf-8"), self.token.encode("utf-8")):
            return True
        previous, deadline = self._previous
        return (previous is not None and time.monotonic() < deadline
                and secrets.compare_digest(token.encode("utf-8"), previous.encode("utf-8")))

    def refusal(self, token) -> str:
        """The refusal text for a rejected `token`: which side's authorization failed, and the command that clears it."""
        try:
            raw = Path(self.key).read_text(encoding="utf-8").strip()
            try:
                parsed = json.loads(raw)
                on_disk = parsed.get("peerToken") if isinstance(parsed, dict) else None
            except ValueError:
                on_disk = raw
        except OSError:
            on_disk = None
        if not isinstance(token, str) or not token:
            side = ("sender side: no token presented; the router could not read this face's key "
                    f"under {self.sessions_dir}")
        elif not isinstance(on_disk, str) or not on_disk:
            side = f"face side: key file {self.key} is unreadable"
        elif not secrets.compare_digest(on_disk.encode("utf-8"), self.token.encode("utf-8")):
            side = f"face side: key file {self.key} disagrees with the live token"
        else:
            side = "sender side: the token held is stale (rotated or from an older face)"
        return (f"not delivered: auth ({side}); clear: "
                f'"{sys.executable}" "{here() / _ROUTER_NAME}" --restart')

    def rotate(self, grace_s) -> float:
        """Mint a new token, accept {old,new} first, then replace the key file; returns the wall-clock grace deadline.

        The old token stays accepted until `grace_s` after the file replacement, so a sender
        holding either file state is never refused before grace ends.
        """
        with self._rotate_lock:
            old, old_previous = self.token, self._previous
            self._previous = (old, float("inf"))
            self.token = secrets.token_hex(16)
            try:
                ROTATE_PAUSE_HOOK()
                for attempt in range(5):
                    try:
                        _roster().write_peer_key(self.key, self._key_data())
                        break
                    except PermissionError:  # Windows: a reader holds the key open for a moment
                        if attempt == 4:
                            raise
                        time.sleep(0.02)
            except BaseException:
                self.token, self._previous = old, old_previous
                raise
            self._previous = (old, time.monotonic() + grace_s)
            return time.time() + grace_s

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
                   owner_pid=None, owner_start=None, leg_mode=None) -> None:
    """Register `name`, take inbound frames on `endpoint`, forward each to the router.

    `owner_pid`/`owner_start` stamp the owning router's identity so a later router can reap this face.
    `leg_mode` is stamped into the registry row (a pending agy leg's face carries "pending").
    """
    reg = Registration(name, endpoint, sessions_dir, cwd=cwd, vendor=vendor, peer=peer, leg_mode=leg_mode)
    if owner_pid and owner_start:
        reg.data.update(unimatrixRouterPid=owner_pid, unimatrixRouterStart=owner_start)
    if transport:
        reg.data.update(unimatrixTransport=True, vendor="transport")

    async def on_conn(reader, writer):
        try:
            raw = await reader.read()
            if not raw.strip():
                return  # liveness probe
            lines = raw.splitlines()
            try:
                lead = json.loads(lines[0])
            except ValueError:
                lead = None
            if isinstance(lead, dict) and lead.get("type") == "auth":
                token, lines = lead.get("token"), lines[1:]
            else:
                token = getattr(reader, "auth_token", None)  # a pipe transport consumes the auth frame and exposes it here
            if not reg.accepts(token):
                # Silence is acceptance, so a refusal must be written.
                try:
                    writer.write((json.dumps({"ok": False, "error": reg.refusal(token)}) + "\n").encode("utf-8"))
                    await writer.drain()
                except OSError:
                    pass
                return
            for line in lines:
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(frame, dict):
                    continue
                if frame.get("op") == "rotate":
                    grace = frame.get("grace_s")
                    try:
                        if isinstance(grace, bool) or not isinstance(grace, (int, float)) or not 0 <= grace <= MAX_GRACE_S:
                            raise ValueError(f"grace_s must be a number in [0, {MAX_GRACE_S}]")
                        until = await asyncio.to_thread(reg.rotate, grace)
                        response = {"ok": True, "grace_until": until}
                    except (OSError, ValueError) as exc:
                        response = {"ok": False, "error": f"rotate failed: {exc}"}
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()
                    return
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

def default_adapters() -> dict:
    """vendor -> async fn(peer, text) -> reply text, loading the adapters on first use."""
    cache = {}  # key -> (source stamp, module)

    def mod(filename, key):
        st = (here() / filename).stat()
        stamp = (st.st_mtime_ns, st.st_size)
        hit = cache.get(key)
        if hit is None or hit[0] != stamp:  # an edited adapter source is reloaded, never served stale
            hit = cache[key] = (stamp, _load(filename, f"unimatrix_peer_{key}"))
        return hit[1]

    async def codex(peer, text):
        m = mod("unimatrix-peer-codex.py", "codex")
        return await m.codex_turn(m.socket_path(), peer["target"], text, tui_held=bool(peer.get("tui")),
                                  on_queued=peer.get("on_queued"), on_echoed=peer.get("on_echoed"))

    async def agy(peer, text):
        m = mod("unimatrix-peer-agy.py", "agy")
        return await m.agy_turn(m.leg_endpoint(peer["target"]), m.transcript_path(peer["target"]), text,
                                wait_reply=not bool(peer.get("deliver_only")))

    async def grok(peer, text):
        m = mod("unimatrix-peer-grok.py", "grok")
        if not peer.get("cwd"):
            return "delivery failed: grok peer has no cwd to pin the resume to"
        return await m.deliver(peer["target"], peer["cwd"], text, runner=m.subprocess.run,
                               home=peer.get("grok_home"))

    return {"codex": codex, "agy": agy, "grok": grok}


class Router:
    """Owns one face child per peer, the control endpoint and the turn locks."""

    last_refusal = ""
    last_resolved_far = False
    last_resolved_row = None  # (name, box) of the one session resolve_sender last matched

    def __init__(self, peers, sessions_dir=None, state_dir=None, endpoint_dir=None,
                 adapters=None, ready_seconds=READY_SECONDS, legs_dir=None,
                 codex_locks_dir=None, presence_dir=None, grok_home=None, peers_file=None) -> None:
        peers = list(peers)
        self.peers_file = str(peers_file) if peers_file else None
        self._peers_stamp = None  # (mtime_ns, size) of peers_file at the last adoption read
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
        self.outbox = {}  # Codex peer name -> {"inflight": item|None, "held": [msg], "failed": [msg id], "p": peer row}
        self.ctl = endpoint_path(ROUTER_ENDPOINT_SEED, self.endpoint_dir)
        self.log_path = os.path.join(self.state_dir, "unimatrix-peer-router.log")
        self.faces = {}  # peer name -> Popen
        self.addressed = {}  # peer name -> one set per open inbound turn: names it sent to during that turn
        self.server = None
        self.tasks = set()
        self.legs_dir = str(legs_dir) if legs_dir else None
        self.codex_locks_dir = str(codex_locks_dir) if codex_locks_dir else None
        self.presence_dir = str(presence_dir) if presence_dir else None
        self.grok_home = str(grok_home) if grok_home else None
        self.discovered = set()  # names found by a scan, not given at construction; only these retire
        self.pending_legs = {}  # name -> agy peer whose leg runs pending (spool only); never in self.peers
        self.pending_faces = set()  # pending_legs names whose face this router spawned; a pending face never enters self.peers
        self.scanner = None
        self.transport_sources = {}  # infrastructure face name -> registered caller name or None
        self.transport_targets = {}  # each infrastructure face is one source/destination conversation
        self.transport_origins = {}  # face name -> the sender name it carried, registered or not
        self.transport_lock = asyncio.Lock()
        self.lease = None  # open router.lock handle, locked for the router lifetime
        self.stop_requested = asyncio.Event()  # set by the shutdown op and by stop signals; serve waits on it
        self.pid_file = None  # router.pid.json path, set only while this router owns the lease
        self.inflight = 0  # control requests being served; a drain waits for them
        self.ctl_ino = None  # inode of the control socket this router bound; None on a pipe
        self.bound_faces = set()  # face endpoints whose child registration reached ready
        self.dead_holders = set()  # Codex peers whose recorded holder is gone: no face, not listed
        self.superseded = {}  # Codex peer name -> name of the face of the same holder that replaced it

    def peer_stale(self, name) -> bool:
        """True for a Codex peer without a live attached holder: dead (False) or unrecorded (None).

        A discovered peer with no recorded holder is live while its writer lock is held; a recorded
        dead holder stays stale.
        """
        peer = self.peers.get(name)
        if not isinstance(peer, dict) or peer.get("vendor") != "codex":
            return False
        if name in self.dead_holders:
            return True
        live = _liveness().codex_holder_live(peer)
        if live is None and name in self.discovered:
            return not self.thread_held(peer.get("target"))
        return live is not True

    async def _drop_dead_holders(self):
        """Refresh fixed Codex holders, recovering live faces and stopping dead ones.

        The row stays in `self.peers` so discovery still treats its target as taken; peers.json is
        never rewritten. A row with no recorded holder is unknown, not dead, and keeps its face.
        """
        if self.peers_file is not None:
            try:
                rows = await asyncio.to_thread(_contract().load_peers, self.peers_file)
            except (OSError, ValueError, _contract().PeerConfigError) as exc:
                self.log("HOLDER-REFRESH-FAILED", type(exc).__name__, exc)
            else:
                current = {(p["name"], p["vendor"], p["target"]): p for p in rows}
                for name, peer in self.peers.items():
                    if peer.get("vendor") != "codex" or name in self.discovered:
                        continue
                    row = current.get((name, "codex", peer["target"]), {})
                    for key in ("codexPid", "codexProcStart"):
                        peer.pop(key, None)
                        if key in row:
                            peer[key] = row[key]
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
            if peer.get("vendor") != "codex" or name in self.discovered:
                continue
            live = _liveness().codex_holder_live(peer)
            if live is True and name in self.dead_holders:
                self.dead_holders.discard(name)
                try:
                    await self._spawn_face(name)
                except Exception as exc:
                    self.log("FACE-REPAIR-FAILED", name, type(exc).__name__, exc)
                continue
            if live is not False or name in self.dead_holders:
                continue
            self.dead_holders.add(name)
            if name in self.faces:
                await self._stop_face(name)
            self.log("holder-gone", name)
        await self._retire_superseded_faces()

    async def _retire_superseded_faces(self) -> None:
        """Keep one face per Codex holder: the other peers' faces are stopped, or never spawned.

        The survivor is the least name, so it is the same face every tick and across its own re-registration.
        The child's own exit unlinks its entry; an external unlink would race the face's rewrite. A superseded
        name revives only once its survivor is no longer a live peer of this router: a survivor mid-restart
        keeps its place, so no other face shows in the gap."""
        faces = [{"name": n, "vendor": "codex", "target": p.get("target")} for n, p in self.peers.items()
                 if p.get("vendor") == "codex" and n not in self.discovered
                 and (n not in self.dead_holders or n in self.superseded)]
        by_id = _liveness().codex_survivors(faces, list(self.peers.values()))
        for face in faces:
            name, survivor = face["name"], by_id.get(id(face))
            if survivor is None:
                if self.superseded.pop(name, None) is not None:
                    self.dead_holders.discard(name)
            elif name not in self.dead_holders:
                self.dead_holders.add(name)
                self.superseded[name] = survivor["name"]
                if name in self.faces:
                    await self._stop_face(name)
                self.log("face-superseded", name, "by", survivor["name"])

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
            try:
                digest = code_digest()
            except (OSError, UnicodeDecodeError):
                digest = None
            _roster().write_json_atomic(self.pid_file, {"pid": os.getpid(),
                                                         "procStart": _roster().proc_start(os.getpid()),
                                                         "codeDigest": digest})
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

    def _live_discovered(self) -> dict:
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
        pending = {}
        if self.legs_dir:
            def leg_scan(tn, tt) -> list:
                found = load_leg_peers(self.legs_dir, tn, tt, pending)
                tt.update(p["target"] for p in pending.values())  # a held presence lock must not list the pending leg ready
                return found
            scans.append(leg_scan)
        if self.presence_dir:
            scans.append(lambda tn, tt: load_lock_peers(self.presence_dir, "agy", tn, tt))
        if self.codex_locks_dir:
            scans.append(lambda tn, tt: load_lock_peers(self.codex_locks_dir, "codex", tn, tt))
        if self.grok_home:
            def grok_scan(tn, tt):
                grok = _sibling("unimatrix-peer-grok.py", "unimatrix_peer_grok")
                found = grok.discover_peers(self.grok_home, _roster().pid_alive, tn, tt)
                for peer in found:
                    peer["grok_home"] = self.grok_home
                return found
            scans.append(grok_scan)
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
        self.pending_legs = {n: p for n, p in pending.items() if n not in live}
        return live

    async def refresh_discovered(self) -> None:
        """Register a face for each newly live discovered peer and retire the ones whose record or lock went."""
        await self.adopt_peers_file()
        await self._drop_dead_holders()
        live = await asyncio.to_thread(self._live_discovered)
        await self._sync_pending_faces()
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

    async def _sync_pending_faces(self) -> None:
        """One face per pending leg: stop the ones whose leg left `pending_legs` (gone, or promoted to a live peer, whose face takes the same endpoint); spawn or repair the rest.

        The face registers `leg_mode: pending`, so the registry mirror carries the row far; a frame
        sent to it spools through the pending branch and never invokes a live turn adapter.
        """
        for name in sorted(self.pending_faces - set(self.pending_legs)):
            if name in self.faces:
                await self._stop_face(name)
            self.pending_faces.discard(name)
        for name in sorted(self.pending_legs):
            if name in self.peers:
                continue
            proc = self.faces.get(name)
            if proc is not None and proc.poll() is None:
                continue
            try:
                if proc is not None:
                    await self._stop_face(name)
                await self._spawn_face(name)
            except Exception as exc:
                self.log("PENDING-FACE-FAILED", name, type(exc).__name__, exc)
                if name in self.faces:
                    await self._stop_face(name)

    async def adopt_peers_file(self) -> None:
        """Adopt Codex rows peers.json gained or changed since the last read; one stat per tick.

        A row for a target a discovered peer holds replaces that peer, so the file's holder fields
        win and no `tui` flag is carried. A changed holder revives a row marked dead. An unreadable
        or invalid file adopts nothing until it changes again.
        """
        if not self.peers_file:
            return
        try:
            st = os.stat(self.peers_file)
        except OSError:
            return
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self._peers_stamp:
            return
        self._peers_stamp = stamp
        try:
            rows = await asyncio.to_thread(_contract().load_peers, self.peers_file)
        except (OSError, ValueError, _contract().PeerConfigError):
            return
        rows = [r for r in rows if r.get("vendor") == "codex"]
        if not rows:
            return
        metadata = await asyncio.to_thread(codex_thread_metadata, self.codex_home)
        for row in rows:
            name, target = row["name"], row["target"]
            if not codex_is_sendable_root(metadata.get(target, {})):
                continue
            current = self.peers.get(name)
            if current is not None and name not in self.discovered:
                if any(current.get(k) != row.get(k) for k in ("codexPid", "codexProcStart")):
                    self.peers[name] = row
                    self.dead_holders.discard(name)
                    try:
                        await (self.restart_face(name) if name in self.faces else self._spawn_face(name))
                    except Exception as e:
                        self.log("ADOPT-REFRESH-FAILED", name, type(e).__name__, e)
                continue
            if any(n not in self.discovered and p["target"] == target for n, p in self.peers.items()):
                continue  # a construction-time row already owns this target
            for n in [n for n, p in self.peers.items()
                      if n in self.discovered and (n == name or p["target"] == target)]:
                await self._retire(n)
            self.peers[name] = row
            self.locks[name] = asyncio.Lock()
            try:
                await self._spawn_face(name)
            except Exception as e:
                self.log("ADOPT-REGISTER-FAILED", name, type(e).__name__, e)
                if name in self.faces:
                    await self._stop_face(name)
                self.peers.pop(name, None)
                self.locks.pop(name, None)
                self.outbox.pop(name, None)
                continue
            self.log("adopted", name)

    async def _retire(self, name):
        """Drop a discovered peer: stop its face, remove its registry files and endpoint."""
        if name in self.faces:
            await self._stop_face(name)
        self.peers.pop(name, None)
        self.locks.pop(name, None)
        self.outbox.pop(name, None)
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
            try:
                for failure in await asyncio.to_thread(_drain_queued_sessions):
                    self.log("QUEUE-DRAIN-FAILED", *failure)
            except Exception as e:
                self.log("QUEUE-DRAIN-FAILED", type(e).__name__, e)

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

    async def _spawn_face(self, name) -> None:
        ep = self.endpoint_of(name)
        pending = name not in self.peers and name in self.pending_legs
        peer = self.pending_legs[name] if pending else self.peers.get(name, {})
        proc = _roster().spawn([_roster().console_python(), str(Path(__file__).resolve()), "face",
                                "--name", name, "--endpoint", ep, "--forward", self.ctl,
                                "--sessions-dir", self.sessions_dir,
                                "--vendor", peer.get("vendor") or "transport",
                                "--peer-json", json.dumps(peer),
                                "--cwd", peer.get("cwd") or os.getcwd(),
                                "--owner-pid", str(os.getpid()),
                                "--owner-start", _roster().proc_start(os.getpid())]
                               + (["--transport"] if name in self.transport_sources else [])
                               + (["--leg-mode", "pending"] if pending else []))
        if pending:
            self.pending_faces.add(name)
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

    async def _stop_face(self, name) -> None:
        old = self.faces.pop(name)
        self.pending_faces.discard(name)
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

    async def drain(self, timeout=DRAIN_SECONDS):
        """Stop accepting control connections, then wait for in-flight requests and delivery tasks; False on timeout."""
        if self.server is not None:
            self.server.close()
        deadline = time.monotonic() + timeout
        while self.inflight > 0 or self.tasks:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.02)
        return True

    async def _on_ctl(self, reader, writer):
        self.inflight += 1
        try:
            await self._serve_ctl(reader, writer)
        finally:
            self.inflight -= 1

    async def _serve_ctl(self, reader, writer):
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

    async def _dispatch(self, req) -> dict:
        op = req.get("op") if isinstance(req, dict) else None
        if op == "inbound":
            peer = req.get("peer")
            if not isinstance(req.get("frame"), dict):
                return {"ok": False, "error": "unknown peer or frame"}
            if peer in self.transport_sources:
                handler = self.handle_transport_inbound
            elif peer in self.peers:
                handler = self.handle_inbound
            elif peer in self.pending_legs:
                handler = self.handle_pending_inbound
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
                    "details": details, "ready": ready, "agents": agents,
                    "codex_pending": {n: self.codex_pending(n) for n, p in listed.items()
                                      if p.get("vendor") == "codex"}}
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
            if isinstance(peer, str) and peer in self.transport_sources:
                # A transport face is never a delivery target: a reply to it goes to the session it carried.
                origin = self.transport_origins.get(peer) or self.transport_sources.get(peer)
                if not (origin and self.transport_sources.get(peer)):
                    return {"ok": False, "error": f"{peer} is a transport face, not a session; its origin "
                            f"{origin or 'is unknown'} has no registered session to reply to"}
                peer = origin
            # A peer's own shell knows its thread/conversation id, not the name the router gave it.
            sender = by_target.get(req.get("as_target")) or str(req.get("as") or "cli")
            as_session = req.get("as_session")
            if (sender not in self.peers and not req.get("as_target") and isinstance(as_session, str) and as_session
                    and self.resolve_sender(as_session)):
                sender = as_session  # the calling session's roster name: a reply to the stamped `from` reaches it
            reply_to = None
            as_target = req.get("as_target")
            if sender not in self.peers and isinstance(as_target, str) and as_target:
                root = await asyncio.to_thread(self.codex_subagent_root, as_target)
                if root == "":
                    return {"ok": False, "error": f"Codex sub-agent {as_target} has no resolvable sendable root parent to reply through"}
                if root:
                    reply_to = by_target.get(root) or root
                    sender = f"codex-{as_target}"
                else:
                    # A pending agy leg is unlisted in self.peers, but the router owns its record: bind the
                    # sender from it (conversation id == target) so CLI agy sessions can still send and reply.
                    pending_self = next((n for n, p in self.pending_legs.items() if p.get("target") == as_target), None)
                    sender = pending_self or await asyncio.to_thread(self.shell_sender, as_target)
                    if not sender:
                        return {"ok": False, "error": "no unique live sender binding; use native SendMessage"}
            pending = next((p for n, p in self.pending_legs.items() if peer in (n, p["target"])), None) \
                if peer not in self.peers and isinstance(peer, str) else None
            if pending is not None:
                if sender == pending["name"]:
                    return {"ok": False, "error": f"cannot send to self ({peer})"}
                if not isinstance(text, str) or is_ack(text):
                    return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
                try:  # the pending leg spools the frame and acks queued; the adapter turns that into QUEUED
                    reply = await self.adapters["agy"]({**pending, "deliver_only": True}, wrap_inbound(sender, text, reply_to))
                except Exception as exc:
                    self.log("TURN-FAILED", pending["name"], type(exc).__name__, exc)
                    reply = f"delivery failed: {exc}"
                if not_delivered(reply):
                    return {"ok": False, "error": str(reply).strip()}
                return {"ok": True, "reply": _contract().label(pending["name"], reply)}
            if peer not in self.peers and isinstance(peer, str):
                if not isinstance(text, str) or is_ack(text):
                    return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
                if reply_to:
                    sender = reply_to
                # A dead holder's face is stopped (an agy leg that dropped to pending), so its endpoint is
                # gone: a send through it fails WinError 2. Its session still replies via a transport face.
                if sender in self.peers and sender not in self.dead_holders:
                    return await self._peer_send_to_session(sender, peer, text)
                return await self._transport_send_to_session(sender, peer, text)
            if peer not in self.peers:
                return {"ok": False, "error": f"no peer named {peer}", "peers": sorted(self.peers)}
            if sender == peer:
                return {"ok": False, "error": f"cannot send to self ({peer})"}
            if not isinstance(text, str) or is_ack(text):
                return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
            if self.peer_stale(peer):
                return {"ok": False, "error": STALE_CODEX_ERROR}
            deliver_only = sender in self.peers and self.peers[peer].get("vendor") == "agy"
            reply = await self.turn(peer, wrap_inbound(sender, text, reply_to), deliver_only=deliver_only)
            if isinstance(reply, dict) and reply.get("user_message_chunk") is True:
                return {"ok": True, "user_message_chunk": True, "session_id": reply.get("session_id"),
                        "msg_id": reply.get("msg_id")}
            if isinstance(reply, dict) and reply.get("written") is True and "reply" not in reply:
                return {"ok": True, "written": True, "msg_id": reply.get("msg_id")}
            if reply == HELD_REPLY:
                return {"ok": True, "held": True, **self.codex_pending(peer)}
            if not_delivered(reply):
                return {"ok": False, "error": str(reply).strip()}
            return {"ok": True, "reply": _contract().label(peer, reply)}
        if op == "rotate":
            peer = req.get("peer")
            if not isinstance(peer, str) or peer not in self.peers:
                return {"ok": False, "error": f"no router-owned peer named {peer}"}
            face = self.endpoint_of(peer)
            try:
                return await asyncio.to_thread(
                    request_line, face, {"op": "rotate", "grace_s": req.get("grace_s", 120)}, 15,
                    _roster().authenticated_data(face, b"", self.sessions_dir))
            except (OSError, ValueError) as exc:
                return {"ok": False, "error": f"face unreachable: {exc}"}
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

    def peer_readiness(self) -> dict:
        """peer name -> True when a send can reach it now; an agy peer is ready only while its leg endpoint exists.

        The ListAgents liveness gates apply on every platform: an agy peer `agy_peer_rows_orphaned`
        reports, or a Codex peer whose `codex_holder_live` is False, is never ready. An unrecorded
        Codex holder (None) is unknown, not dead, and keeps its row.
        """
        ready = {}
        metadata = codex_thread_metadata(self.codex_home) if any(p.get('vendor') == 'codex' for p in self.peers.values()) else {}
        orphaned = self._orphaned_agy_targets() if any(p.get('vendor') == 'agy' for p in self.peers.values()) else set()
        for name, p in self.peers.items():
            if name in self.dead_holders:
                continue
            ok = p.get('vendor') != 'codex' or codex_is_sendable_root(metadata.get(p.get('target'), {}))
            if p.get("vendor") == "agy" and os.name != "nt":
                m = _sibling("unimatrix-peer-agy.py", "unimatrix_peer_agy_ready")
                ok = os.path.exists(m.leg_endpoint(p["target"]))
            if p.get("vendor") == "agy" and p.get("target") in orphaned:
                ok = False
            if ok and p.get("vendor") == "codex" and _liveness().codex_holder_live(p) is False:
                ok = False
            ready[name] = ok
        return ready

    @staticmethod
    def _orphaned_agy_targets() -> set:
        """Targets of the agy peers.json rows ListAgents drops as orphaned; empty when the probe cannot read."""
        try:
            return {target for _, target in _liveness().agy_peer_rows_orphaned()}
        except OSError:
            return set()

    def roster_rows(self, sender="cli", ready=None) -> tuple:
        """(reachable names, one {name, box, vendor} row per reachable name).

        A name backed only by relay-pushed mirror rows carries `mirror_only: True`: no live session is
        evidenced behind it, so a listing never calls it ready.

        Reachable: a peer that is ready, or an external roster session whose registered endpoint
        exists; never `sender` itself. This is the set a send from `sender` can resolve now.
        """
        ready = self.peer_readiness() if ready is None else ready
        entries, backed = {}, set()
        roster = _roster()
        try:
            files = os.listdir(self.sessions_dir)
        except FileNotFoundError:
            files = []
        loaded = []
        for filename in files:
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.sessions_dir, filename), encoding="utf-8") as file:
                    entry = json.load(file)
            except (OSError, ValueError):
                continue
            if isinstance(entry, dict):
                loaded.append(entry)
        for entry in loaded:
            name = entry.get("name")
            if (not isinstance(name, str) or name in self.peers or name in self.transport_sources
                    or entry.get("unimatrixTransport") or not isinstance(entry.get("pid"), int)
                    or not roster.pid_alive(entry["pid"]) or not self.external_codex_sendable(entry)):
                continue
            # resolve_send_target refuses a mirror the listing predicate hides; listing it would print a name --to cannot reach.
            if (entry.get(roster.FAR_SOCKET_FIELD) or entry.get("unimatrixRemote")) and not roster.listed_row(entry, loaded):
                continue
            if not _push_only_mirror(entry):
                backed.add(name)
            if name in entries and (entry.get("startedAt") or 0) < (entries[name].get("startedAt") or 0):
                continue
            entries[name] = entry
        names = {name for name, ok in ready.items() if ok} | set(self.pending_legs)
        for name, entry in entries.items():
            endpoint = entry.get("messagingSocketPath")
            if endpoint and _transport().endpoint_exists(endpoint):
                names.add(name)
        names.discard(sender)
        contract = _contract()
        box = contract.local_box()
        rows = [{"name": n, "box": box, "vendor": self.peers[n]["vendor"], "this_box": True,
                 **({"stale": True} if self.peer_stale(n) else {})} if n in self.peers
                else {"name": n, "box": box, "vendor": "agy", "this_box": True, "leg_mode": "pending"}
                if n in self.pending_legs
                else {**contract.agent_row(entries[n], box),
                      **({"mirror_only": True} if n not in backed else {})} for n in sorted(names)]
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

    def codex_pending(self, peer) -> dict:
        """What the Codex peer's outbox holds: messages queued or held and not yet echoed, the oldest's age, failures."""
        box = self.outbox.get(peer) or {}
        inflight = box.get("inflight")
        msgs = (inflight["msgs"] if inflight else []) + box.get("held", [])
        oldest = min((m["received"] for m in msgs), default=None)
        return {"pending": len(msgs), "oldest_age_s": round(time.time() - oldest, 1) if oldest else 0.0,
                "failed": list(box.get("failed", []))}

    def _coalesce(self, msgs) -> str:
        """One queue item from held messages, oldest first, each headed with its sender and send time."""
        n = len(msgs)
        parts = [f"[{n} message{'s' if n != 1 else ''} arrived while you were mid-turn; oldest first]"]
        for i, m in enumerate(msgs, 1):
            when = time.strftime("%H:%M:%S", time.localtime(m["received"]))
            parts.append(f"--- {i}/{n} from {m['sender']} at {when} ---\n{m['text']}")
        return "\n\n".join(parts)

    def _on_echo(self, peer, item) -> None:
        """The adapter saw `item` start as a Codex turn: log each message, then flush what was held."""
        box = self.outbox.get(peer)
        if box is None or item["echoed"]:
            return
        item["echoed"] = True
        now = time.time()
        for m in item["msgs"]:
            self.log("INJECTED", peer, m["id"], time.strftime("echo=%H:%M:%S", time.localtime(now)),
                     f"latency_s={now - m['received']:.1f}")
        if box["inflight"] is item:
            box["inflight"] = None
        self._flush_held(peer)

    def _flush_held(self, peer) -> None:
        """Enqueue everything held for `peer` as ONE item, as a router-owned task; a no-op while an item is unechoed."""
        box = self.outbox.get(peer)
        if box is None or box["inflight"] is not None or not box["held"]:
            return
        msgs, box["held"] = box["held"], []
        item = {"msgs": msgs, "text": self._coalesce(msgs), "echoed": False}
        box["inflight"] = item
        task = asyncio.get_running_loop().create_task(self._flush_task(peer, item))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _flush_task(self, peer, item) -> None:
        ids = ",".join(m["id"] for m in item["msgs"])
        try:
            reply = await self._run_codex_item(peer, item)
        except Exception as e:
            self.log("TURN-FAILED", peer, type(e).__name__, e)
            return
        self.log("HARVESTED", peer, ids, str(reply).strip()[:200])  # held senders get no routed reply

    async def _run_codex_item(self, peer, item, on_queued=None) -> str:
        """Run `item` through the Codex adapter; a stranded item is enqueued once more, a second miss is recorded.

        When the adapter returns without the echo having been seen (socket turn, exec fallback, no
        rollout), inflight is cleared and the held messages flush so the peer never wedges."""
        box = self.outbox[peer]
        p = {**box["p"], "on_queued": on_queued, "on_echoed": lambda: self._on_echo(peer, item)}
        try:
            reply = await self.adapters["codex"](p, item["text"])
            if reply == STRANDED_REPLY and not item["echoed"]:
                self.log("STRANDED", peer, ",".join(m["id"] for m in item["msgs"]), "re-enqueue")
                reply = await self.adapters["codex"](p, item["text"])
                if reply == STRANDED_REPLY and not item["echoed"]:
                    ids = [m["id"] for m in item["msgs"]]
                    self.log("STRAND-FAILED", peer, ",".join(ids))
                    box["failed"] = (box["failed"] + ids)[-20:]
                    return "delivery failed: queued item stranded twice and was not delivered"
            return reply
        finally:
            if box["inflight"] is item:
                box["inflight"] = None
                self._flush_held(peer)

    async def turn(self, peer, text, addressed=None, deliver_only=False) -> str:
        """One adapter turn for `peer` under its lock; a failure becomes the reply text.

        `addressed`, when given, collects the names the peer sent to by its own addressed send
        during this turn, so the caller can skip the harvested reply for those. A Codex peer with an
        unechoed item in its queue holds the message instead and returns HELD_REPLY.
        """
        p = self.peers[peer]
        lock = self.locks[peer]
        await lock.acquire()
        held = True

        def release():
            # The lock orders enqueues, not replies: a queued Codex message must not wait on an earlier turn's reply.
            nonlocal held
            if held:
                held = False
                lock.release()

        if addressed is not None:
            self.addressed.setdefault(peer, []).append(addressed)
        try:
            try:
                if self.peer_stale(peer):
                    return f"delivery failed: {STALE_CODEX_ERROR}"
                if p["vendor"] == "codex":
                    metadata = await asyncio.to_thread(codex_thread_metadata, self.codex_home)
                    if not codex_is_sendable_root(metadata.get(p['target'], {})):
                        return 'delivery failed: Codex target is not an independently sendable root'
                if p["vendor"] == "codex" and not p.get("tui") and self.thread_held(p["target"]):
                    p = {**p, "tui": True}
                if deliver_only and p["vendor"] == "agy":
                    p = {**p, "deliver_only": True}
                if p["vendor"] == "codex":
                    msg_id = uuid.uuid4().hex[:12]
                    named = re.match(r"\[([^\]\n]+)\] ", text)  # wrap_inbound's `[sender] ` head
                    msg = {"id": msg_id, "sender": named.group(1) if named else "unknown",
                           "received": time.time(), "text": text}
                    self.log("INBOUND", peer, msg_id, f"from={msg['sender']}",
                             time.strftime("received=%H:%M:%S", time.localtime(msg["received"])))
                    box = self.outbox.setdefault(peer, {"inflight": None, "held": [], "failed": [], "p": p})
                    box["p"] = p
                    if box["inflight"] is not None:
                        box["held"].append(msg)
                        self.log("HELD", peer, msg_id, f"pending={self.codex_pending(peer)['pending']}")
                        return HELD_REPLY
                    item = {"msgs": [msg], "text": text, "echoed": False}
                    box["inflight"] = item
                    return await self._run_codex_item(peer, item, on_queued=release)
                return await self.adapters[p["vendor"]](p, text)
            except Exception as e:
                self.log("TURN-FAILED", peer, type(e).__name__, e)
                return f"delivery failed: {e}"
        finally:
            release()
            if addressed is not None:
                open_turns = [t for t in self.addressed.get(peer, []) if t is not addressed]
                if open_turns:
                    self.addressed[peer] = open_turns
                else:
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

    async def _transport_face(self, source, destination) -> str:
        """Lazily register a genuine transport sender for one source/destination conversation."""
        name = readable_peer_name("unimatrix", source + "\0" + destination, "transport")
        async with self.transport_lock:
            self.transport_sources[name] = source if self.resolve_sender(source) else None
            self.transport_targets[name] = destination
            self.transport_origins[name] = source
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
                    self.transport_origins.pop(name, None)
                    raise
        return name

    def resolve_relay_target(self, name) -> dict:
        """Strict relay target for the live local session called `name`; the answer an inbound relay delivers by.

        {"ok": True, "endpoint", "name", "box"} for exactly one live session. Otherwise a refusal
        that is logged either way (RELAY-TARGET / RELAY-REFUSED); an unknown or ambiguous name is
        never mapped to another session or a default inbox.
        """
        endpoint = self.resolve_sender(name) if isinstance(name, str) and name else ""
        if not endpoint and isinstance(name, str) and name in self.peers:
            # resolve_sender skips the router's own faces (they are never a Claude reply target), but a
            # Codex/agy peer's inbox IS its face: an inbound relay delivers there, as a local send does.
            if self.peer_stale(name):
                self.last_refusal = STALE_CODEX_ERROR
            elif (self.faces.get(name) is not None and self.faces[name].poll() is None
                    and name not in self.dead_holders):
                endpoint = self.endpoint_of(name)
                self.last_resolved_row = (name, _contract().local_box())
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

    async def _transport_send_to_session(self, source, to, text) -> dict:
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
                # A sender with no registered session has no `<source>.<box>` row anywhere; the face is the
                # only addressable identity carrying this frame, so a reply goes to it, not to a ghost.
                frame = routable_from(frame, f"{source}.{box}" if self.resolve_sender(source) else transport)
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

    async def _deliver_as_peer(self, peer, endpoint, frame) -> None:
        """Send through the registered face so the OS client PID matches frame.from."""
        face = self.endpoint_of(peer)
        response = await asyncio.to_thread(request_line, face,
            {"op": "deliver", "endpoint": endpoint, "frame": frame}, 15,
            _roster().authenticated_data(face, b"", self.sessions_dir))
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
        for turn_set in self.addressed.get(peer, ()):
            turn_set.add(to)
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

    def shell_sender(self, session_id):
        """Return the unique live local session name bound to a shell's native session ID."""
        matches = set()
        for row in self._session_rows():
            if (row.get("sessionId") != session_id or not _liveness().entry_live(row)
                    or row.get("unimatrixRemote") or row.get("macSocketPath")
                    or row.get("unimatrixRouterPid")):
                continue
            name, endpoint = row.get("name"), row.get("messagingSocketPath")
            if isinstance(name, str) and name and isinstance(endpoint, str) and endpoint:
                matches.add((name, endpoint))
        if len(matches) != 1:
            return ""
        name, endpoint = matches.pop()
        return name if self.resolve_sender(name) == endpoint else ""

    def _listed_twin(self, row) -> dict | None:
        """The one listed mirror of the same far session when `row` is an unlisted mirror of it, else None.

        A far session reached through two ssh aliases of one box is mirrored twice and the listing shows
        one; an address that lands on the hidden mirror reaches the session the listing shows."""
        roster = _roster()
        sock, remote = row.get(roster.FAR_SOCKET_FIELD), row.get("unimatrixRemote")
        if not (sock and remote) or not row.get("messagingSocketPath"):
            return None
        rows = self._session_rows()
        if roster.listed_row(row, rows):
            return None
        twins = [r for r in rows
                 if r.get(roster.FAR_SOCKET_FIELD) == sock and r.get("unimatrixRemote")
                 and roster.box_key(r["unimatrixRemote"]) == roster.box_key(remote)
                 and r.get("messagingSocketPath") and r["messagingSocketPath"] != row["messagingSocketPath"]
                 and r.get("sessionId") == row.get("sessionId") and roster.listed_row(r, rows)
                 and isinstance(r.get("pid"), int) and roster.pid_alive(r["pid"])
                 and self.external_codex_sendable(r) and not _far_alias_is_stale(r)]
        return twins[0] if len(twins) == 1 else None

    def resolve_sender(self, name, fallback="") -> str:
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
            if (not isinstance(e, dict) or name not in [*_contract().mirror_addresses(e), *_contract().projected_addresses(e),
                                                        *_box_id_aliases(e)]
                    or name in self.peers or name in self.transport_sources):
                continue
            ep, pid = e.get("messagingSocketPath"), e.get("pid")
            if not ep or not isinstance(pid, int) or not _roster().pid_alive(pid):
                continue
            if not _off_windows() and _transport().is_pipe(ep) and not _transport().endpoint_exists(ep):
                continue  # a stale row's dead pipe must neither win nor make the live row ambiguous
            if not self.external_codex_sendable(e):
                refused_identity = True
                continue
            if _far_alias_is_stale(e) or _ref_contradicts_session(e, name):
                refused_identity = True
                continue
            owned_alias = owned_alias or name in _contract().projected_addresses(e)
            # A Claude Code row carries no vendor; a relay-pushed mirror of the same session must not
            # read as a second owner beside the bridge mirror that stamps vendor "claude".
            owner = (e.get('vendor') or 'claude', e.get('target') or e.get('sessionId') or ep)
            owners.add(owner)
            ep_owners.setdefault(ep, set()).add(owner)
            (exact if e.get("name") == name else aliases).add(ep)
            rows_by_ep[ep] = e
            if e.get("unimatrixFarName") or e.get("unimatrixRemote") or e.get("macSocketPath"):
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
        if len(matches) > 1 and len(owners) == 1:
            # One session behind several routes (the roster's bridge mirror and a relay-pushed mirror)
            # is one address, not ambiguity: prefer the bridge mirror, then the exact name.
            matches = {min(matches, key=lambda ep: (not rows_by_ep[ep].get("unimatrixFarName"), ep not in exact, ep))}
        if len(matches) > 1:
            named = ", ".join(sorted(f"{rows_by_ep[ep].get('name')}@{ep}" for ep in matches))
            self.last_refusal = f"ambiguous: {len(matches)} live sessions carry this name: {named}"
            return ""  # An exact name never beats a far alias: both are live carriers of the address.
        if len(matches) == 1:
            twin = self._listed_twin(rows_by_ep[next(iter(matches))])
            if twin:
                matches, far_eps = {twin["messagingSocketPath"]}, {twin["messagingSocketPath"]}
                rows_by_ep[twin["messagingSocketPath"]] = twin
        self.last_resolved_far = bool(matches) and matches <= far_eps
        if matches:
            row = rows_by_ep[next(iter(matches))]
            self.last_resolved_row = (row.get("name"), _contract().agent_row(row, _contract().local_box())["box"])
            return next(iter(matches))
        return fallback

    async def handle_pending_inbound(self, peer, frame) -> None:
        """A frame at a pending leg's face: spool it through the agy leg (deliver_only); no turn runs and no reply routes back."""
        pending = self.pending_legs.get(peer)
        if pending is None:
            self.log("PENDING-LEG-GONE", peer)
            return
        _, sender_name, body = _contract().parse_inbound(frame)
        if is_ack(body) or body.lstrip().lower().startswith("[reply]"):
            self.log("DROPPED-ACK", sender_name, "->", peer)
            return
        try:
            reply = await self.adapters["agy"]({**pending, "deliver_only": True}, wrap_inbound(sender_name, body))
        except Exception as exc:
            self.log("TURN-FAILED", peer, type(exc).__name__, exc)
            return
        self.log("PENDING-QUEUED" if not not_delivered(reply) else "PENDING-NOT-DELIVERED", peer, "<-", sender_name)

    async def handle_inbound(self, peer, frame):
        sender_ep, sender_name, body = _contract().parse_inbound(frame)
        if is_ack(body) or body.lstrip().lower().startswith("[reply]"):
            self.log("DROPPED-ACK", sender_name, "->", peer)
            return
        addressed = set()
        reply = await self.turn(peer, wrap_inbound(sender_name, body), addressed)
        if isinstance(reply, dict) and reply.get("user_message_chunk") is True:
            self.log("CHUNK", peer, reply.get("session_id"))
            return
        if isinstance(reply, dict) and reply.get("written") is True:
            self.log("HELD-WROTE", peer, reply.get("msg_id"))
            return
        if reply == HELD_REPLY:
            return  # the coalesced item's reply is harvested and logged by the outbox, not routed back
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
        await router.drain()
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
    target = _sibling("unimatrix-send.py", "unimatrix_send_router").own_target() if a.as_name == "cli" else ""
    try:
        resp = request_line(ctl, {"op": "send", "as": a.as_name, "as_target": target,
                                  "to": a.peer, "text": " ".join(a.text)})
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
    if resp.get("user_message_chunk") is True:
        print(f"user_message_chunk {resp.get('session_id')}")
        return 0
    if resp.get("written") is True:
        print(f"sent to {a.peer}")
        return 0
    delivered = ", ".join(f"{k}={resp[k]}" for k in ("msg_id", "sender") if k in resp)
    print(f"delivered to {a.peer}" + (f" ({delivered})" if delivered else "") + "; the router returned no reply field")
    print("router-version mismatch: the running router answers with an older or different send reply shape; "
          "restart the router (stop the running unimatrix-peer-router.py and start it again)", file=sys.stderr)
    return 0


def cmd_face(argv) -> int:
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
    p.add_argument("--leg-mode", default=None)
    a = p.parse_args(argv)
    asyncio.run(run_face(a.name, a.endpoint, a.forward, a.sessions_dir, a.cwd, a.transport, a.vendor,
                         json.loads(a.peer_json), a.owner_pid, a.owner_start, a.leg_mode))
    return 0


def cmd_restart(argv):
    p = argparse.ArgumentParser(prog="unimatrix-peer-router.py --restart")
    p.add_argument("--restart", action="store_true")
    p.add_argument("--from", dest="src", default=None, help="stamp scripts directory holding unimatrix-install.py")
    p.add_argument("--dest", default=None, help="installed unimatrix directory (default: <settings home>/unimatrix)")
    a = p.parse_args(argv)
    src = Path(a.src) if a.src else here()
    if not (src / "unimatrix-install.py").is_file():
        print(f"no unimatrix-install.py in {src}; pass --from <stamp scripts directory>", file=sys.stderr)
        return 2
    spec = importlib.util.spec_from_file_location("unimatrix_install_stamp", src / "unimatrix-install.py")
    installer = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(installer)
        dest = Path(a.dest) if a.dest else _roster().delivery_settings_home() / "unimatrix"
        copied = installer.install_scripts(src, dest)
        print(f"refreshed {len(copied)} scripts into {dest} from {src}")
        res = installer.restart_installed_router(dest, print) or {}
    except Exception as e:
        print(f"router restart failed: {e}", file=sys.stderr)
        return 1
    finally:
        sys.dont_write_bytecode = keep
    print(f"router restarted: {res.get('stopped')} old pid {res.get('old_pid')} new pid {res.get('new_pid')}")
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
                             presence_dir=default_presence_dir(), peers_file=peers_file,
                             grok_home=_sibling("unimatrix-peer-grok.py", "unimatrix_peer_grok").grok_home())))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "face":
        return cmd_face(argv[1:])
    if argv and argv[0] == "send":
        return cmd_send(argv[1:])
    if "--restart" in argv:
        return cmd_restart(argv)
    return cmd_serve(argv)


if __name__ == "__main__":
    sys.exit(main())
