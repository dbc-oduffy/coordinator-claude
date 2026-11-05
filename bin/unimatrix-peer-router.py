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
POSIX only: asyncio unix-socket streams do not exist on Windows.
"""
import argparse
import asyncio
import importlib.util
import json
import os
import re
import secrets
import shlex
import signal
import socket
import sys
import time
from pathlib import Path

READY_SECONDS = 15
SEND_TIMEOUT = 900
ROUTER_ENDPOINT_SEED = "unimatrix-peer-router"
FRAME_LIMIT = 1 << 22
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


def _contract():
    """The peer contract module, loaded on first use."""
    return _sibling("unimatrix-peer-contract.py", "unimatrix_peer_contract")


def default_peers_file():
    """The peers file a default invocation reads."""
    return _roster().settings_home() / "unimatrix" / "peers.json"


def default_legs_dir():
    """Where the agy launch hook writes one leg record per conversation."""
    return _roster().settings_home() / "unimatrix" / "agy-legs"


def load_leg_peers(legs_dir, taken_names=(), taken_targets=()):
    """Peers for every live agy leg record in `legs_dir`: name agy-<conversation>, target the conversation.

    A record whose leg pid is dead, whose name or conversation is already `taken_*` (peers.json
    wins), or that is unreadable is skipped.
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
            conv, pid = rec["conversation"], int(rec["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(conv, str) or not conv or conv in taken_targets or not _roster().pid_alive(pid):
            continue
        name = f"agy-{conv}"
        if name in taken_names:
            continue
        peers.append({"name": name, "vendor": "agy", "target": conv})
    return peers


def default_codex_locks_dir():
    """Where Codex keeps one writer lock per live thread: $CODEX_HOME (else ~/.codex)/thread-writer-locks."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "thread-writer-locks"


def default_presence_dir():
    """Where agy keeps one presence lock per live conversation: next to its brain root (AGY_BRAIN_DIR)."""
    brain = os.environ.get("AGY_BRAIN_DIR")
    root = Path(brain).parent if brain else Path.home() / ".gemini" / "antigravity-cli"
    return root / "presence"


def lock_held(path):
    """True while another process holds any flock on `path`; a free or unreadable file is not live.

    Probes with an exclusive lock so a holder in shared mode still reads as held. Without
    `fcntl` (Windows) nothing is discoverable, so nothing is live.
    """
    try:
        import fcntl
    except ImportError:
        return False
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


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
    for f in names:
        ident = f[:-len(".lock")]
        if f.startswith(".") or not f.endswith(".lock") or not ident or ident in taken_targets:
            continue
        name = f"{vendor}-{ident}"
        if name in taken_names or not lock_held(os.path.join(lock_dir, f)):
            continue
        peers.append({"name": name, "vendor": vendor, "target": ident})
    return peers


SEND_SCRIPT = "unimatrix-send.py"
NO_REPLY_MARKERS = {"[unimatrix-peer-codex] no reply before timeout"}
NOT_DELIVERED_PREFIXES = ("[unimatrix-peer-agy] not delivered", "[unimatrix-peer-agy] delivery failed",
                          "delivery failed:")


def not_delivered(reply):
    """True when an adapter reply says the message never reached the peer."""
    return str(reply or "").lstrip().startswith(NOT_DELIVERED_PREFIXES)


def wrap_inbound(sender, body):
    """What a peer sees: `[<sender>] <body>` plus a trailer naming the sender and the exact reply command."""
    # Run through the interpreter, never the exec bit: Windows has none (check_posix_exec_assumptions).
    send = f"{shlex.quote(sys.executable)} {shlex.quote(str(here() / SEND_SCRIPT))}"
    return (f"[{sender}] {body}\n\nFrom agent {sender}, not the PM. "
            f"Never answer them in plain text to the human at your keyboard. "
            f"Reply to them with: {send} --to {shlex.quote(str(sender))} '<your reply>'")


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
    ep = _roster().local_endpoint(seed)
    if endpoint_dir:
        return os.path.join(endpoint_dir, os.path.basename(ep))
    return ep


def peer_endpoint(name, endpoint_dir=None):
    return endpoint_path(f"unimatrix-peer-{name}", endpoint_dir)


def _private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)


def bind_private_server(path):
    """Bind a unix socket file that is 0600 from creation."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    _private_dir(os.path.dirname(path))
    old = os.umask(0o177)
    try:
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(path)
    finally:
        os.umask(old)
    os.chmod(path, 0o600)
    srv.listen(32)
    srv.setblocking(False)
    return srv


def request_line(endpoint, request, timeout=SEND_TIMEOUT):
    """Send one JSON line to a local endpoint and return the one-line JSON answer."""
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


class Registration:
    """A registry entry plus its 0600 key file for one endpoint, keyed by the writing pid."""

    def __init__(self, name, endpoint, sessions_dir, cwd=None):
        self.pid = os.getpid()
        self.endpoint = endpoint
        self.sessions_dir = sessions_dir
        self.token = secrets.token_hex(32)
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
        }

    def write(self):
        _private_dir(self.sessions_dir)
        fd = os.open(self.key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self.token)
        _roster().write_json_atomic(self.entry, self.data)

    def remove(self):
        for p in (self.entry, self.key, self.endpoint):
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

async def run_face(name, endpoint, forward, sessions_dir):
    """Register `name`, take inbound frames on `endpoint`, forward each to the router."""
    reg = Registration(name, endpoint, sessions_dir)

    async def on_conn(reader, writer):
        raw = await reader.read()
        writer.close()
        if not raw.strip():
            return  # liveness probe
        for line in raw.splitlines():
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            if isinstance(frame, dict) and frame.get("type") == "user":
                try:
                    await asyncio.to_thread(request_line, forward,
                                            {"op": "inbound", "peer": name, "frame": frame}, 15)
                except (OSError, ValueError):
                    pass

    _private_dir(os.path.dirname(endpoint))
    try:
        os.unlink(endpoint)
    except FileNotFoundError:
        pass
    old = os.umask(0o177)
    try:
        server = await asyncio.start_unix_server(on_conn, path=endpoint, limit=FRAME_LIMIT)
    finally:
        os.umask(old)
    os.chmod(endpoint, 0o600)
    reg.write()
    stop = asyncio.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(s, stop.set)
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

    return {"codex": codex, "agy": agy}


class Router:
    """Owns one face child per peer, the control endpoint and the turn locks."""

    def __init__(self, peers, sessions_dir=None, state_dir=None, endpoint_dir=None,
                 adapters=None, ready_seconds=READY_SECONDS, legs_dir=None,
                 codex_locks_dir=None, presence_dir=None):
        self.peers = {p["name"]: p for p in peers}
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
        self.discovered = set()  # names found by a scan, not given at construction; only these retire
        self.scanner = None

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
            _private_dir(os.path.dirname(self.ctl))
            self.server = await self._bind_control()
            for name in list(self.peers):
                await self._spawn_face(name)
            if self.legs_dir or self.codex_locks_dir or self.presence_dir:
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
        scans = []
        if self.legs_dir:
            scans.append(lambda tn, tt: load_leg_peers(self.legs_dir, tn, tt))
        if self.presence_dir:
            scans.append(lambda tn, tt: load_lock_peers(self.presence_dir, "agy", tn, tt))
        if self.codex_locks_dir:
            scans.append(lambda tn, tt: load_lock_peers(self.codex_locks_dir, "codex", tn, tt))
        for scan in scans:
            for peer in scan(names | set(live), targets):
                live.setdefault(peer["name"], peer)
        return live

    async def refresh_discovered(self):
        """Register a face for each newly live discovered peer and retire the ones whose record or lock went."""
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
        _unlink(self.endpoint_of(name))
        self.peers.pop(name, None)
        self.locks.pop(name, None)
        self.discovered.discard(name)
        self.log("retired", name)

    async def _scan_discovered(self):
        while True:
            await asyncio.sleep(LEG_SCAN_SECONDS)
            try:
                await self.refresh_discovered()
            except Exception as e:
                self.log("DISCOVER-SCAN-FAILED", type(e).__name__, e)

    async def _spawn_face(self, name):
        ep = self.endpoint_of(name)
        proc = _roster().spawn([sys.executable, str(Path(__file__).resolve()), "face",
                                "--name", name, "--endpoint", ep, "--forward", self.ctl,
                                "--sessions-dir", self.sessions_dir])
        self.faces[name] = proc
        await self._wait(f"face {name}",
                         lambda p=proc: os.path.exists(os.path.join(self.sessions_dir, f"{p.pid}.json")),
                         proc)
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

    async def _bind_control(self):
        try:
            os.unlink(self.ctl)
        except FileNotFoundError:
            pass
        old = os.umask(0o177)
        try:
            server = await asyncio.start_unix_server(self._on_ctl, path=self.ctl, limit=FRAME_LIMIT)
        finally:
            os.umask(old)
        os.chmod(self.ctl, 0o600)
        return server

    async def stop(self):
        """Remove every entry, key, endpoint, key file and child this router wrote."""
        if self.scanner is not None:
            self.scanner.cancel()
            self.scanner = None
        if self.server is not None:
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
        for name in self.faces:
            _unlink(self.endpoint_of(name))
        self.faces = {}
        _unlink(self.ctl)

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
            if peer not in self.peers or not isinstance(req.get("frame"), dict):
                return {"ok": False, "error": "unknown peer or frame"}
            t = asyncio.create_task(self.handle_inbound(peer, req["frame"]))
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)
            return {"ok": True}
        if op == "list":
            return {"ok": True, "peers": sorted(self.peers), "sessions": await asyncio.to_thread(self.session_names),
                    "ready": await asyncio.to_thread(self.peer_readiness)}
        if op == "send":
            peer, text = req.get("to"), req.get("text")
            # A peer's own shell knows its thread/conversation id, not the name the router gave it.
            by_target = {p.get("target"): n for n, p in self.peers.items()}
            sender = by_target.get(req.get("as_target")) or str(req.get("as") or "cli")
            if peer not in self.peers and sender in self.peers and isinstance(peer, str):
                if not isinstance(text, str) or is_ack(text):
                    return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
                return await self._peer_send_to_session(sender, peer, text)
            if peer not in self.peers:
                return {"ok": False, "error": f"no peer named {peer}", "peers": sorted(self.peers)}
            if not isinstance(text, str) or is_ack(text):
                return {"ok": False, "error": "empty or acknowledgement text is not delivered"}
            reply = await self.turn(peer, wrap_inbound(sender, text))
            if not_delivered(reply):
                return {"ok": False, "error": str(reply).strip()}
            return {"ok": True, "reply": _contract().label(peer, reply)}
        return {"ok": False, "error": "unknown op"}

    def peer_readiness(self):
        """peer name -> True when a send can reach it now; an agy peer is ready only while its leg endpoint exists."""
        ready = {}
        for name, p in self.peers.items():
            ok = True
            if p.get("vendor") == "agy" and os.name != "nt":
                m = _sibling("unimatrix-peer-agy.py", "unimatrix_peer_agy_ready")
                ok = os.path.exists(m.leg_endpoint(p["target"]))
            ready[name] = ok
        return ready

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
            if (isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"] not in self.peers
                    and isinstance(e.get("pid"), int) and _roster().pid_alive(e["pid"])):
                names.add(e["name"])
        return sorted(names)

    async def _peer_send_to_session(self, peer, to, text):
        """A peer's own addressed send to a Claude session `to`; marks the peer's open turn as answered."""
        ep = self.resolve_sender(to)
        if not ep:
            return {"ok": False, "error": f"no session named {to}", "peers": sorted(self.peers)}
        p = self.peers[peer]
        frame = _contract().build_frame(self.endpoint_of(peer), peer, _contract().label(peer, text))
        frame = _contract().stamp(frame, peer, p["vendor"], p["target"], os.getpid())
        try:
            await asyncio.to_thread(deliver, ep, (json.dumps(frame) + "\n").encode("utf-8"))
        except Exception as e:
            self.log("POST-FAILED", peer, "->", to, type(e).__name__, e)
            return {"ok": False, "error": f"delivery to {to} failed: {e}"}
        if peer in self.addressed:
            self.addressed[peer].add(to)
        self.log("SENT", peer, "->", to, frame["msg_id"])
        return {"ok": True, "msg_id": frame["msg_id"]}

    def resolve_sender(self, name, fallback=""):
        """Current messaging endpoint of the live roster session called `name`, else `fallback`.

        Re-read on every reply, so a sender that restarted under a new pid/endpoint keeps its
        name as its address. The router's own faces never match a Claude sender.
        """
        best = None
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
            if not isinstance(e, dict) or e.get("name") != name or name in self.peers:
                continue
            ep, pid = e.get("messagingSocketPath"), e.get("pid")
            if not ep or not isinstance(pid, int) or not _roster().pid_alive(pid):
                continue
            rank = e.get("startedAt") or 0
            if best is None or rank > best[0]:
                best = (rank, ep)
        return best[1] if best else fallback

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
        sender_ep = self.resolve_sender(sender_name, sender_ep)
        p = self.peers[peer]
        frame = _contract().build_frame(self.endpoint_of(peer), peer, f"[reply] {peer}: {str(reply).strip()}")
        frame = _contract().stamp(frame, peer, p["vendor"], p["target"], os.getpid())
        try:
            await asyncio.to_thread(deliver, sender_ep, (json.dumps(frame) + "\n").encode("utf-8"))
        except Exception as e:
            self.log("POST-FAILED", peer, "->", sender_name, type(e).__name__, e)
            return
        resp = {"ok": True, "msg_id": frame["msg_id"]}
        self.log("REPLIED", peer, "->", sender_name, resp)


def deliver(endpoint, data):
    """Write `data` to a session's unix socket."""
    s = socket.socket(socket.AF_UNIX)
    try:
        s.settimeout(10)
        s.connect(endpoint)
        s.sendall(data)
    finally:
        s.close()


def _unlink(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


async def serve(router):
    await router.start()
    stop = asyncio.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(s, stop.set)
    try:
        await stop.wait()
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
    except OSError as e:
        print(f"router not reachable at {ctl}: {e}", file=sys.stderr)
        return 1
    if not resp.get("ok"):
        print(resp.get("error", "failed"), file=sys.stderr)
        if resp.get("peers"):
            print("peers: " + ", ".join(resp["peers"]), file=sys.stderr)
        return 1
    print(resp["reply"])
    return 0


def cmd_face(argv):
    p = argparse.ArgumentParser(prog="unimatrix-peer-router.py face")
    p.add_argument("--name", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--forward", required=True)
    p.add_argument("--sessions-dir", required=True)
    a = p.parse_args(argv)
    asyncio.run(run_face(a.name, a.endpoint, a.forward, a.sessions_dir))
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
                             presence_dir=default_presence_dir())))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if sys.platform == "win32":
        print("unimatrix-peer-router: POSIX only (unix-socket streams)", file=sys.stderr)
        return 2
    if argv and argv[0] == "face":
        return cmd_face(argv[1:])
    if argv and argv[0] == "send":
        return cmd_send(argv[1:])
    return cmd_serve(argv)


if __name__ == "__main__":
    sys.exit(main())
