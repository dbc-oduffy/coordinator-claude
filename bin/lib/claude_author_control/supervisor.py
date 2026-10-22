"""Platform-agnostic core of claude-author --control-socket: idle gate, op dispatch, status,
discovery file, child env/argv, and the ``run()`` entrypoint.

OS legs (``relay_posix``/``relay_windows``, ``transport_posix``/``transport_windows``) are
imported lazily by ``os.name``. Each leg module exposes ``spawn(argv, env, observers) -> Relay``
(relay modules) or ``make_transport(instance, instance_dir) -> Transport`` (transport modules).
A relay MAY expose ``set_service_hook(service, next_timeout)``: the loop then calls
``service()`` when ``next_timeout()`` elapses, so force deliveries run on the relay's own
loop; without it the supervisor's timer thread services them. The handler passed to
``Transport.serve`` is the Supervisor itself: ``sup(req, peer) -> dict`` waits for a forced
delivery, while ``sup.submit(req, peer, reply)`` replies by callback: a transport sharing a
selectors loop uses it so no force settle ever blocks that loop.
"""
from __future__ import annotations

import heapq
import importlib
import importlib.util
import itertools
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    from claude_author_control import protocol as P
except ImportError:  # loaded by path with no package on sys.path
    _spec = importlib.util.spec_from_file_location(
        "claude_author_control_protocol_by_path", Path(__file__).with_name("protocol.py"))
    P = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = P
    _spec.loader.exec_module(P)

ENV_STRIP = ("CLAUDE_CODE_CHILD_SESSION",)
SESSION_ARG_FLAGS = ("--resume", "-r", "--continue", "-c", "--session-id")
HOOK_EVENTS = P.TURN_EVENTS
DISCOVERY_REFRESH_S = 1.0
TRANSPORT_BIND_TIMEOUT_S = 5.0
FORCE_REPLY_GRACE_S = 5.0


def _env_ms(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
        return v if v >= 0 else default
    except ValueError:
        return default


def _has_session_arg(argv: list[str]) -> bool:
    for a in argv:
        for flag in SESSION_ARG_FLAGS:
            if a == flag or (flag.startswith("--") and a.startswith(flag + "=")):
                return True
    return False


def build_child_env(base_env: dict[str, str]) -> dict[str, str]:
    """Copy of ``base_env`` without the nested-session marker."""
    return {k: v for k, v in base_env.items() if k not in ENV_STRIP}


def _epoch(ts) -> Optional[float]:
    """turn.json's ``ts`` (the hook writes ISO-8601 UTC with ``Z``) as epoch seconds, so it
    compares with the supervisor's wall-clock override. Unparseable is None, never a match."""
    if isinstance(ts, (int, float)):
        return float(ts)
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def settings_json(instance_dir: str, hook_path: str) -> str:
    """The ``--settings`` payload registering the turn hook; the control dir travels in hook
    args, never in the environment."""
    entry = [{"hooks": [{"type": "command", "command": sys.executable,
                         "args": [hook_path, instance_dir]}]}]
    return json.dumps({"hooks": {ev: entry for ev in HOOK_EVENTS}}, separators=(",", ":"))


def build_child_argv(full_argv: list[str], instance_dir: str,
                     hook_path: Optional[str] = None) -> tuple[list[str], Optional[str]]:
    """Return (argv, minted_session_id). A ``--session-id`` is minted only when the caller
    passed none of --session-id/--resume/--continue; ``--settings`` is always appended."""
    argv = list(full_argv)
    minted = None
    if not _has_session_arg(argv):
        minted = str(uuid.uuid4())
        argv += ["--session-id", minted]
    hook = hook_path or str(Path(__file__).with_name("turn_hook.py").resolve())
    argv += ["--settings", settings_json(instance_dir, hook)]
    return argv, minted


class _Deadlines:
    """Deadline heap serviced by whoever calls ``service``; nothing here sleeps."""

    def __init__(self, clock: Callable[[], float]):
        self._clock = clock
        self._heap: list = []
        self._seq = itertools.count()
        self._lock = threading.Lock()
        self.wake = threading.Event()

    def add(self, delay_s: float, fn: Callable[[], None]) -> None:
        with self._lock:
            heapq.heappush(self._heap, (self._clock() + delay_s, next(self._seq), fn))
        self.wake.set()

    def next_timeout(self) -> Optional[float]:
        with self._lock:
            if not self._heap:
                return None
            return max(0.0, self._heap[0][0] - self._clock())

    def service(self) -> int:
        ran = 0
        while True:
            with self._lock:
                if not self._heap or self._heap[0][0] > self._clock():
                    return ran
                _, _, fn = heapq.heappop(self._heap)
            fn()
            ran += 1


class Supervisor:
    """Gate, dispatch and status over an injected Relay. Also the relay's ``Observers``."""

    def __init__(self, instance_dir: str, *, clock: Callable[[], float] = time.monotonic,
                 wallclock: Callable[[], float] = time.time,
                 idle_ms: Optional[int] = None, settle_ms: Optional[int] = None):
        self.instance_dir = instance_dir
        self.relay = None
        self.clock = clock
        self.wallclock = wallclock
        self.idle_ms = idle_ms if idle_ms is not None else _env_ms(P.ENV_IDLE_MS, P.DEFAULT_IDLE_MS)
        self.settle_ms = (settle_ms if settle_ms is not None
                          else _env_ms(P.ENV_FORCE_SETTLE_MS, P.DEFAULT_FORCE_SETTLE_MS))
        self.write_lock = threading.RLock()
        self.deadlines = _Deadlines(clock)
        self.last_key: Optional[float] = None
        self.draft_dirty = False
        self.paste_mode = False
        self._mode_tail = b""
        self.known_session_id: Optional[str] = None
        self._override: Optional[tuple[float, float]] = None  # (wall ts, since) turn_active=False

    # ------------------------------------------------------------ observers
    def on_input(self, data: bytes) -> None:
        with self.write_lock:
            self.last_key = self.clock()
            self._track_draft(data)

    def _track_draft(self, data: bytes) -> None:
        if data == P.ESC:
            self.draft_dirty = False
            return
        if data.startswith(P.PASTE_START):
            self.draft_dirty = True
            return
        if data.startswith(P.ESC):
            return  # a cursor/function-key sequence edits nothing
        for b in data:
            if b in (0x0D, 0x03, 0x15):
                self.draft_dirty = False
            elif b >= 0x20 and b != 0x7F:
                self.draft_dirty = True

    def on_output(self, data: bytes) -> None:
        buf = self._mode_tail + data
        on, off = buf.rfind(P.PASTE_MODE_ON), buf.rfind(P.PASTE_MODE_OFF)
        if on >= 0 or off >= 0:
            self.paste_mode = on > off
        self._mode_tail = buf[-(len(P.PASTE_MODE_ON) - 1):]

    # ------------------------------------------------------------ state
    def user_idle_ms(self) -> Optional[int]:
        if self.last_key is None:
            return None
        return max(0, int((self.clock() - self.last_key) * 1000))

    def gate_closed(self) -> bool:
        idle = self.user_idle_ms()
        return self.draft_dirty or (idle is not None and idle < self.idle_ms)

    def read_turn(self) -> Optional[dict]:
        try:
            with open(os.path.join(self.instance_dir, P.TURN_FILE), "r", encoding="utf-8") as f:
                rec = json.load(f)
            return rec if isinstance(rec, dict) else None
        except (OSError, ValueError):
            return None

    def turn_state(self) -> tuple[bool, str, Optional[float]]:
        """(turn_active, turn_source, turn_since). A supervisor-set inactive state holds until
        the hook writes a turn.json newer than it."""
        rec = self.read_turn()
        hook_ts = _epoch(rec.get("ts")) if rec else None
        if self._override is not None and (hook_ts is None or hook_ts <= self._override[0]):
            return False, "supervisor", self._override[0]
        if rec is None:
            return False, "none", None
        return bool(rec.get("turn_active")), "hook", hook_ts

    def session_id(self) -> Optional[str]:
        rec = self.read_turn()
        sid = rec.get("session_id") if rec else None
        return sid if isinstance(sid, str) and sid else self.known_session_id

    def status(self) -> dict:
        active, source, since = self.turn_state()
        return {
            "alive": bool(self.relay.alive()) if self.relay else False,
            "child_pid": getattr(self.relay, "pid", None),
            "session_id": self.session_id(),
            "turn_active": active, "turn_source": source, "turn_since": since,
            "user_idle_ms": self.user_idle_ms(), "draft_dirty": self.draft_dirty,
            "paste_mode": self.paste_mode,
        }

    def _supervisor_ended_turn(self) -> None:
        self._override = (self.wallclock(), self.clock())

    # ------------------------------------------------------------ dispatch
    def handle(self, req, peer) -> dict:
        """Blocking form: waits (on an Event, not a sleep) for a forced delivery's reply."""
        box: list = []
        done = threading.Event()

        def reply(resp: dict) -> None:
            box.append(resp)
            done.set()

        self.submit(req, peer, reply)
        if not done.is_set():
            done.wait(self.settle_ms / 1000.0 + FORCE_REPLY_GRACE_S)
        return box[0] if box else P.error_response(req.id, "pty_dead", "no reply from supervisor")

    def __call__(self, req, peer) -> dict:
        return self.handle(req, peer)

    def submit(self, req, peer, reply: Callable[[dict], None]) -> None:
        """Dispatch ``req``; ``reply`` is called exactly once, inline except for a forced
        delivery, which replies from the deadline that services the settle window."""
        ident = P.identity_for(peer, req.on_behalf_of)
        try:
            if req.op == "status":
                reply(P.ok_response(req.id, None, ident, self.status()))
                return
            self._write_op(req, ident, reply)
        except P.ProtocolError as e:
            reply(P.error_response(req.id, e.code, e.msg))

    def _write_op(self, req, ident: dict, reply) -> None:
        if self.relay is None or not self.relay.alive():
            raise P.ProtocolError("pty_dead", "child process is not running")
        force = req.force and req.op in P.FORCE_OPS
        with self.write_lock:
            if self.gate_closed():
                raise P.ProtocolError("busy_user", "user is active at the keyboard")
            # Validate and encode before any byte lands, so a bad request never leaves an Esc.
            data = P.encode_op(req.op, req.args, self.paste_mode,
                               on_behalf_of=req.on_behalf_of, relayed=True)
            if req.op == "interrupt":
                self.relay.write(data)
                self._supervisor_ended_turn()
                reply(P.ok_response(req.id, "injected", ident))
                return
            if not force:
                active = req.op in ("prompt", "compact") and self.turn_state()[0]
                self.relay.write(data)
                reply(P.ok_response(req.id, "queued" if active else "injected", ident))
                return
            self.relay.write(P.FORCE_PREFIX)
            self._supervisor_ended_turn()
        self.deadlines.add(self.settle_ms / 1000.0,
                           lambda: self._deliver_forced(req, ident, reply))

    def _deliver_forced(self, req, ident: dict, reply) -> None:
        try:
            with self.write_lock:
                if self.relay is None or not self.relay.alive():
                    raise P.ProtocolError("pty_dead", "child exited during the force settle")
                if self.gate_closed():
                    raise P.ProtocolError(
                        "busy_user", "keystroke during force settle; Esc already sent, "
                                     "text not delivered")
                self.relay.write(P.encode_op(req.op, req.args, self.paste_mode,
                                             on_behalf_of=req.on_behalf_of, relayed=True))
            reply(P.ok_response(req.id, "injected", ident))
        except P.ProtocolError as e:
            reply(P.error_response(req.id, e.code, e.msg))

    def service(self) -> None:
        self.deadlines.service()

    def next_timeout(self) -> Optional[float]:
        return self.deadlines.next_timeout()


class Discovery:
    """Instance dir + discovery file lifecycle."""

    def __init__(self, control_base: str, instance: str):
        self.base = Path(control_base)
        self.instance = instance
        self.instance_dir = self.base / instance
        self.sessions_dir = self.base / P.SESSIONS_DIRNAME
        self.path = self.sessions_dir / f"{instance}.json"
        self.record: Optional[dict] = None

    @staticmethod
    def _mkdir_private(path: Path) -> None:
        path.mkdir(mode=P.DIR_MODE, parents=True, exist_ok=True)
        os.chmod(path, P.DIR_MODE)  # umask cannot widen; chmod also tightens a pre-existing dir

    def create_dirs(self) -> None:
        self._mkdir_private(self.base)
        self._mkdir_private(self.sessions_dir)
        self._mkdir_private(self.instance_dir)

    def write(self, record: dict) -> None:
        self.record = record
        tmp = self.sessions_dir / f".{self.instance}.{os.getpid()}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, P.FILE_MODE)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(record, separators=(",", ":")))
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, P.FILE_MODE)
            os.replace(tmp, self.path)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def refresh(self, session_id: Optional[str], child_pid: Optional[int]) -> None:
        rec = self.record
        if rec is None or (rec["session_id"] == session_id and rec["child_pid"] == child_pid):
            return
        self.write({**rec, "session_id": session_id, "child_pid": child_pid})

    def cleanup(self) -> None:
        import shutil
        try:
            os.unlink(self.path)
        except OSError:
            pass
        shutil.rmtree(self.instance_dir, ignore_errors=True)


def _load_leg(name: str):
    # Under claude-author the package is registered in sys.modules, and the legs' relative
    # `from . import protocol` only resolves when they load as its submodules. The by-path
    # branch serves a supervisor loaded outside the package (tests).
    if __package__:
        return importlib.import_module(f"{__package__}.{name}")
    spec = importlib.util.spec_from_file_location(
        f"claude_author_control_{name}", Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _select_legs():
    """(spawn, make_transport) for this OS; imports only the matching leg."""
    suffix = "windows" if os.name == "nt" else "posix"
    return (_load_leg(f"relay_{suffix}").spawn,
            _load_leg(f"transport_{suffix}").make_transport)


def run(full_argv: list[str], *, plugin_dir: str, control_base: str) -> int:
    """Supervise ``full_argv`` (claude + its args) under a PTY with a control socket;
    returns the child's exit code. ``plugin_dir`` is accepted for the pinned entrypoint
    signature; the hook and OS legs resolve beside this file."""
    instance = uuid.uuid4().hex[: P.INSTANCE_HEX_LEN]
    disc = Discovery(control_base, instance)
    transport = None
    stop = threading.Event()
    try:
        spawn, make_transport = _select_legs()
        disc.create_dirs()
        sup = Supervisor(str(disc.instance_dir))
        argv, minted = build_child_argv(full_argv, str(disc.instance_dir))
        sup.known_session_id = minted
        transport = make_transport(instance, str(disc.instance_dir))
        # Bind before spawning, so a bind failure leaves no child behind, and before the
        # discovery write, so no client connects to an address nothing listens on.
        threading.Thread(target=_serve, args=(transport, sup), daemon=True).start()
        ready = getattr(transport, "ready", None)  # a pipe transport is bound at construction
        if ready is not None and not ready.wait(TRANSPORT_BIND_TIMEOUT_S):
            raise RuntimeError("control transport did not bind")
        sup.relay = spawn(argv, build_child_env(dict(os.environ)), sup)
        child_pid = getattr(sup.relay, "pid", None)
        disc.write(P.discovery_record(
            instance=instance, session_id=minted,
            transport="pipe" if os.name == "nt" else "unix", address=transport.address,
            supervisor_pid=os.getpid(), child_pid=child_pid, cwd=os.getcwd(),
            started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        hook = getattr(sup.relay, "set_service_hook", None)
        if hook is not None:
            hook(sup.service, sup.next_timeout)
    except BaseException as e:
        if transport is not None:
            _safe_close(transport)
        disc.cleanup()
        print(f"claude-author --control-socket: supervisor failed to start: {e}",
              file=sys.stderr)
        return 1

    def timer() -> None:
        while not stop.is_set():
            sup.deadlines.service()
            disc.refresh(sup.session_id(), child_pid)
            t = sup.next_timeout()
            sup.deadlines.wake.wait(DISCOVERY_REFRESH_S if t is None else min(t, DISCOVERY_REFRESH_S))
            sup.deadlines.wake.clear()

    threading.Thread(target=timer, daemon=True).start()
    try:
        run_loop = getattr(sup.relay, "run", None)  # POSIX relays pump on this thread
        return int(run_loop() if run_loop is not None else sup.relay.wait())
    finally:
        stop.set()
        sup.deadlines.wake.set()
        _safe_close(transport)
        disc.cleanup()


def _serve(transport, sup: Supervisor) -> None:
    try:
        transport.serve(sup)
    except Exception as e:  # a dead transport must not kill the session
        print(f"claude-author --control-socket: transport stopped: {e}", file=sys.stderr)


def _safe_close(transport) -> None:
    try:
        transport.close()
    except Exception:
        pass
