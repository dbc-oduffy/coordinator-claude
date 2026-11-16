"""One ssh carrier per far box, addressed by member host name (else the IP as given) and pinned with HostKeyAlias.

`channel(box, key=, host=)` is the only way the roster poll, the bridge relay and the inbox reach a
far box. A far box recorded POSIX (`far_platform`) rides one ssh ControlMaster per box (the roster's
`mux_options`); a Windows or unrecorded far box never gets ControlMaster options. Windows OpenSSH has
no ControlMaster, so `run` goes through a per-box broker that owns one long-lived `ssh <host> mux`
carrier and multiplexes NDJSON request frames over it; against a far relay with no `mux` mode the
broker serves each request as a single-flight one-shot ssh, which still holds the far sshd to one
connection at a time. Loadable by path (bin scripts load siblings via spec_from_file_location).
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
BIN = Path(__file__).resolve().parent.parent
BROKER_IDLE_SECONDS = 600.0
RESTART_FLOOR_SECONDS = 20.0
BROKER_START_WAIT_SECONDS = 8.0
_IP_HOSTS = {}
IP_HOSTS_TTL_SECONDS = 300.0
ADDRESS_TTL_SECONDS = 30.0
_VERIFIED = {}


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0


_LOAD_LOCK = threading.RLock()


def _sibling(path, key):
    with _LOAD_LOCK:
        mod = sys.modules.get(key)
        if mod is None:
            spec = importlib.util.spec_from_file_location(key, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[key] = mod
            spec.loader.exec_module(mod)
        return mod


def _roster():
    return sys.modules.get("unimatrix_roster") or _sibling(BIN / "unimatrix-roster.py", "unimatrix_roster")


def _liveness():
    return _sibling(BIN / "unimatrix-liveness.py", "unimatrix_box_mux_liveness")


def refuse_real(kind, value):
    """Raise unimatrix_test_home.TestHomeRefusal when a test home would reach a real `kind`; else a no-op."""
    if not os.environ.get("UNIMATRIX_TEST_HOME"):
        return
    path = Path(__file__).resolve().parent / "unimatrix_test_home.py"
    if path.is_file():
        _sibling(path, "unimatrix_test_home").refuse_real(kind, value)


def is_ip_literal(host):
    h = str(host).strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ipaddress.ip_address(h.split("%", 1)[0])
        return True
    except ValueError:
        return False


def member_ip_hosts():
    """ip literal -> member host name from the verified membership, cached; {} when membership is unusable."""
    now = time.monotonic()
    hit = _IP_HOSTS.get("v")
    if hit and now < hit[1]:
        return hit[0]
    try:
        found = _sibling(BIN / "unimatrix-send.py", "unimatrix_send_mux")._member_ip_hosts()
    except Exception:
        found = {}
    _IP_HOSTS["v"] = (found, now + (IP_HOSTS_TTL_SECONDS if found else 30.0))
    return found


def box_of(host):
    """The box id of a host: an IP literal is its own id (`:` -> `-`, file-name safe); else first dot label, no trailing `-lan`, lowercase."""
    h = str(host).rpartition("@")[2]
    if is_ip_literal(h):
        return h.strip("[]").lower().replace(":", "-")
    label = h.partition(".")[0].lower()
    return label[:-4] if label.endswith("-lan") else label


def resolve_remote(remote, ip_hosts=None):
    """(ssh target, box id) for `remote`; an IP literal is replaced by its member host name when membership maps it.

    An unmapped IP stays as dialled, its box id the IP itself (so HostKeyAlias=<ip>): no membership, no refusal."""
    user, _, host = str(remote).rpartition("@")
    if is_ip_literal(host):
        named = (ip_hosts if ip_hosts is not None else member_ip_hosts()).get(host.strip("[]").lower())
        if named and not is_ip_literal(named):
            host = named
    return (f"{user}@{host}" if user else host), box_of(host)


def ssh_argv(box, key, host, extra=()):
    """The ssh argv up to (not including) the remote command: key, batch mode, HostKeyAlias=<box>, keepalive.

    `extra` leads the options: ssh keeps the first value of a repeated -o, so a caller's keepalive overrides the default."""
    return ["ssh", *extra, "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", f"HostKeyAlias={box}",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
            host]


def _fault(command, ex):
    return subprocess.CompletedProcess([command], 255, b"", f"{type(ex).__name__}: {ex}".encode())


class DirectChannel:
    """One ssh per call; on POSIX the `mux_options` ControlMaster turns them into one connection per box."""

    def __init__(self, box, key, host, extra=(), mux_options=None):
        self.box, self.key, self.host = box, key, host
        self.extra, self._mux_options = list(extra), mux_options

    def _argv(self):
        mux = self._mux_options(self.host) if self._mux_options else []
        return ssh_argv(self.box, self.key, self.host, [*self.extra, *mux])

    def run(self, command, data=b"", timeout=30):
        """ssh `command` with `data` on stdin; any fault is a returncode-255 result."""
        try:
            return subprocess.run([*self._argv(), command], input=data, capture_output=True, timeout=timeout,
                                  creationflags=_no_window())
        except Exception as ex:
            return _fault(command, ex)

    def subscribe(self, command, data=b""):
        """Start the long-lived `command` (inbox streams), write `data` to its stdin, return the Popen."""
        p = subprocess.Popen([*self._argv(), command], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, creationflags=_no_window())
        p.stdin.write(data)
        p.stdin.flush()
        return p


def _b64(b):
    return base64.b64encode(b or b"").decode("ascii")


def lock_path(home, box):
    return Path(home) / "unimatrix" / "mux" / f"{box}.lock"


def read_lock(path):
    try:
        rec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def lock_live(rec):
    """True when the lock's pid is alive and its start stamp still matches (a reused pid is not a broker)."""
    lv = _liveness()
    pid = rec.get("pid")
    try:
        return isinstance(pid, int) and lv.pid_alive(pid) and lv.proc_start(pid) == rec.get("procStart")
    except OSError:
        return False


class BrokerChannel(DirectChannel):
    """`run` rides the box's broker (started on demand); `subscribe` stays one stream per call."""

    def __init__(self, box, key, host, home, extra=(), spawn_broker=None):
        super().__init__(box, key, host, extra)
        self.home = Path(home)
        self._spawn = spawn_broker or self._spawn_detached

    def _spawn_detached(self):
        flags = _no_window() | getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([_roster().console_python(), str(Path(__file__).resolve()), "broker", "--box", self.box, "--host", self.host,
                          "--key", self.key, "--home", str(self.home), *[f"--extra={e}" for e in self.extra]],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags, close_fds=True)

    def _lock(self):
        path = lock_path(self.home, self.box)
        rec = read_lock(path)
        if rec is not None and not lock_live(rec):
            try:
                path.unlink()
            except OSError:
                pass
            rec = None
        if rec is None:
            refuse_real("far_box", self.host)
            refuse_real("key_path", self.key)
            self._spawn()
            deadline = time.monotonic() + BROKER_START_WAIT_SECONDS
            while rec is None and time.monotonic() < deadline:
                time.sleep(0.05)
                rec = read_lock(path)
            if rec is None:
                raise OSError(f"broker for {self.box} did not start")
        return rec

    def run(self, command, data=b"", timeout=30):
        """The one-connection send: a returncode-255 result on any fault."""
        try:
            rec = self._lock()
            req = json.dumps({"cmd": command, "data": _b64(data), "timeout": timeout}).encode() + b"\n"
            with socket.create_connection(("127.0.0.1", rec["port"]), timeout=timeout + 5) as s:
                s.sendall(str(rec["token"]).encode() + b"\n" + req)
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
            reply = json.loads(buf)
            return subprocess.CompletedProcess([command], reply["rc"], base64.b64decode(reply["stdout"]),
                                               base64.b64decode(reply["stderr"]))
        except Exception as ex:
            return _fault(command, ex)


_FAR_PLATFORM = {}
_ALIAS_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")  # the filename rule of unimatrix-install control_far_record_path
UNKNOWN_FAR_PLATFORM_TTL_SECONDS = 30.0
_POSIX_DOMAINS = ("darwin", "linux")


def _platform_class(value):
    """'win32' | 'posix' | None for a probe platform ('win32', 'darwin', 'linux') or a pidDomain ('win32:<host>')."""
    v = str(value or "").strip().lower()
    if v == "win32" or v.startswith("win32:"):
        return "win32"
    return "posix" if v in _POSIX_DOMAINS else None


def _recorded_far_platform(box):
    """The platform class of far `box` from the control-far record, else from a mirror session entry, else None."""
    roster = _roster()
    safe = _ALIAS_UNSAFE.sub("-", box)
    try:
        rec = json.loads((Path(roster.settings_home()) / "unimatrix" / "control-far" / f"{safe}.json").read_text(encoding="utf-8"))
        found = _platform_class(rec.get("platform")) if isinstance(rec, dict) else None
    except (OSError, ValueError):
        found = None
    if found:
        return found
    sessions = Path(roster.sessions_dir())
    try:
        names = sorted(os.listdir(sessions))
    except OSError:
        return None
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            entry = json.loads((sessions / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # A mirror's own `pidDomain` is the local bridge's; the far session's is `farPidDomain`.
        if isinstance(entry, dict) and str(entry.get("box") or "").lower() == box.lower():
            found = _platform_class(entry.get("farPidDomain"))
            if found:
                return found
    return None


def far_platform(box):
    """'win32', 'posix' or None (unknown) for far `box`, from records on disk only; cached per process per box.

    A known platform is cached for the process; an unknown one for UNKNOWN_FAR_PLATFORM_TTL_SECONDS so a record
    written later (unimatrix-install, a new mirror) is picked up."""
    now = time.monotonic()
    hit = _FAR_PLATFORM.get(box)
    if hit and (hit[0] is not None or now < hit[1]):
        return hit[0]
    found = _recorded_far_platform(box)
    _FAR_PLATFORM[box] = (found, now + UNKNOWN_FAR_PLATFORM_TTL_SECONDS)
    return found


def channel(box, *, key, host, home=None, extra=(), direct=False, mux_options=None, win=None,
            spawn_broker=None):
    """The channel to far `box`, dialled at member host name `host`; never connects at construction.

    `direct=True` or a non-Windows `win` gives a DirectChannel, ControlMaster-backed only when `far_platform(box)`
    is 'posix' (a Windows or unrecorded far box gets no Control* option, whatever `mux_options` the caller
    passes); Windows gives the broker-backed channel, which under a test home refuses to start a broker for a box
    or key the C1 guard calls real."""
    if direct or not (IS_WIN if win is None else win):
        if mux_options is None:
            mux_options = lambda h: _roster().mux_options(h, key)
        if far_platform(box) != "posix":
            # Windows sshd replays a master's first command to later channels: a send lands in the wrong session.
            mux_options = lambda h: []
        return DirectChannel(box, key, host, extra, mux_options)
    return BrokerChannel(box, key, host, home or _roster().settings_home(), extra, spawn_broker)


def _far_addresses():
    return _sibling(Path(__file__).resolve().parent / "unimatrix_far_addresses.py", "unimatrix_far_addresses")


def machine_local_value(name):
    """The machine-local value of `name` (one reader spawn), '' when the reader is missing or fails."""
    reader = _roster().settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return ""
    try:
        try:
            from coordinator_core import machine_local_spawn
        except ImportError:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from cc_invoke import ensure_engine_on_path

            ensure_engine_on_path(str(BIN / "unimatrix-roster.py"))
            from coordinator_core import machine_local_spawn
        value, ok = machine_local_spawn.get(str(reader), name)
    except Exception:  # no engine on this box: the value reads as unset
        return ""
    return value.strip() if ok and value else ""


def verified_host(host, box, key, *, connect=None, read_key=None, verify=None, now=time.monotonic):
    """`host` while its name accepts a TCP connection; else `user@<address>` of the first listed address of `box`
    whose host key verifies, else `host`. A reachable name spawns nothing; either outcome of a failed name is cached
    for ADDRESS_TTL_SECONDS so repeated dials neither re-probe nor re-read the list. The caller keeps `box` as the channel's box id (HostKeyAlias)."""
    far = _far_addresses()
    user, _, name = host.rpartition("@")
    connect = connect or getattr(far, "tcp_connect", None)
    if connect is None:
        print("unimatrix: installed unimatrix_far_addresses lacks tcp_connect; upgrade it (version skew); "
              f"dialling {host} unverified", file=sys.stderr)
        return host
    if is_ip_literal(name):
        return host
    hit = _VERIFIED.get((box, user))
    if hit and now() < hit[1]:
        return hit[0]
    if connect(name):
        return host
    addresses = far.box_addresses(box, read_key or machine_local_value)
    address = None
    if addresses:
        address, _skipped = far.first_answering(box, user, addresses, connect=connect,
                                                verify=verify or far.make_verify(box, key))
    found = far.target_for(user, address) if address else host
    _VERIFIED[(box, user)] = (found, now() + ADDRESS_TTL_SECONDS)
    return found


def for_remote(remote, *, key, ip_hosts=None, connect=None, read_key=None, verify=None, **kw):
    """`channel` for an ssh `remote` (alias or user@host): an IP remote is mapped to its member host name first.

    When that host name fails a TCP connect, the channel dials the box's first host-key-verified listed address
    (`verified_host`) with the box id, so HostKeyAlias, unchanged."""
    host, box = resolve_remote(remote, ip_hosts)
    host = verified_host(host, box, key, connect=connect, read_key=read_key, verify=verify)
    return channel(box, key=key, host=host, **kw)


class Broker:
    """Owns one `ssh <host> mux` carrier for `box` and serves local clients over a token-guarded loopback port."""

    def __init__(self, box, key, host, home, extra=(), argv_factory=None, idle=BROKER_IDLE_SECONDS,
                 restart_floor=RESTART_FLOOR_SECONDS):
        self.box, self.key, self.host, self.home = box, key, host, Path(home)
        self._factory = argv_factory or (lambda: ssh_argv(box, key, host, extra))
        self.idle, self.restart_floor = idle, restart_floor
        self.degraded = False
        self.stopped = threading.Event()
        self._lock = threading.Lock()
        self._oneshot = threading.Lock()
        self._wlock = threading.Lock()
        self._pending = {}
        self._next_id = 0
        self._proc = None
        self._started_at = None
        self._last_use = time.monotonic()
        self._sock = None
        self._stderr = bytearray()

    def _ensure_carrier(self):
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._proc
            if self._started_at is not None and time.monotonic() - self._started_at < self.restart_floor:
                raise OSError(f"carrier to {self.box} restarted inside {self.restart_floor:g}s; not redialling")
            self._started_at = time.monotonic()
            self._stderr = bytearray()
            p = subprocess.Popen([*self._factory(), "mux"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, creationflags=_no_window())
            self._proc = p
            threading.Thread(target=self._drain_stderr, args=(p, self._stderr), daemon=True).start()
            threading.Thread(target=self._read_replies, args=(p,), daemon=True).start()
            return p

    @staticmethod
    def _drain_stderr(p, sink):
        for raw in p.stderr:
            if len(sink) < 4096:
                sink.extend(raw)

    def _read_replies(self, p):
        for line in p.stdout:
            try:
                reply = json.loads(line)
            except ValueError:
                continue
            slot = self._pending.get(reply.get("id")) if isinstance(reply, dict) else None
            if slot is not None:
                slot["result"] = reply
                slot["event"].set()
        p.wait()
        # An old far relay answers `usage:` to `mux`: serve every request one-shot from here on.
        if bytes(self._stderr).lstrip().startswith(b"usage:"):
            self.degraded = True
        for slot in list(self._pending.values()):
            slot["event"].set()

    def _one_shot(self, cmd, data, timeout):
        with self._oneshot:
            try:
                r = subprocess.run([*self._factory(), cmd], input=data, capture_output=True, timeout=timeout,
                                   creationflags=_no_window())
            except Exception as ex:
                r = _fault(cmd, ex)
        return {"rc": r.returncode, "stdout": _b64(r.stdout), "stderr": _b64(r.stderr)}

    def handle(self, req):
        """The reply dict for one client request {cmd, data, timeout}."""
        self._last_use = time.monotonic()
        cmd, data = req["cmd"], base64.b64decode(req.get("data") or "")
        timeout = float(req.get("timeout") or 30)
        if not self.degraded:
            try:
                p = self._ensure_carrier()
                with self._wlock:
                    self._next_id += 1
                    rid = self._next_id
                    slot = self._pending[rid] = {"event": threading.Event(), "result": None}
                    p.stdin.write(json.dumps({"id": rid, "cmd": cmd, "data": _b64(data)}).encode() + b"\n")
                    p.stdin.flush()
                slot["event"].wait(timeout)
                self._pending.pop(rid, None)
                if slot["result"] is not None:
                    r = slot["result"]
                    return {"rc": r.get("rc", 255), "stdout": r.get("stdout", ""), "stderr": r.get("stderr", "")}
                if not self.degraded:
                    tail = bytes(self._stderr)[-300:]
                    return {"rc": 255, "stdout": "", "stderr": _b64(b"carrier ended: " + tail)}
            except OSError as ex:
                return {"rc": 255, "stdout": "", "stderr": _b64(f"{type(ex).__name__}: {ex}".encode())}
        return self._one_shot(cmd, data, timeout)

    def _serve_client(self, conn, token):
        with conn:
            conn.settimeout(10)
            f = conn.makefile("rb")
            if f.readline().strip() != token.encode():
                return
            req = json.loads(f.readline())
            conn.settimeout(None)
            conn.sendall(json.dumps(self.handle(req)).encode() + b"\n")

    def serve(self):
        """Take the box lock, then serve until idle or stopped; releases the lock and the carrier on exit."""
        path = lock_path(self.home, self.box)
        path.parent.mkdir(parents=True, exist_ok=True)
        token = os.urandom(16).hex()
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(64)
        self._sock.settimeout(1.0)
        lv = _liveness()
        rec = {"pid": os.getpid(), "procStart": lv.proc_start(os.getpid()), "port": self._sock.getsockname()[1], "token": token}
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            held = read_lock(path)
            if held is not None and lock_live(held):
                self._sock.close()
                return
            path.unlink(missing_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        try:
            while not self.stopped.is_set() and time.monotonic() - self._last_use < self.idle:
                try:
                    conn, _ = self._sock.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._serve_client, args=(conn, token), daemon=True).start()
        finally:
            path.unlink(missing_ok=True)
            self._sock.close()
            with self._lock:
                if self._proc is not None and self._proc.poll() is None:
                    self._proc.terminate()


def main(argv=None):
    p = argparse.ArgumentParser(prog="unimatrix_box_mux.py")
    p.add_argument("mode", choices=["broker"])
    p.add_argument("--box", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--home", required=True)
    p.add_argument("--extra", action="append", default=[])
    a = p.parse_args(argv)
    refuse_real("far_box", a.host)
    refuse_real("key_path", a.key)
    Broker(a.box, a.key, a.host, a.home, a.extra).serve()


if __name__ == "__main__":
    main()
