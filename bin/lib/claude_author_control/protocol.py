"""Protocol v0 for claude-author --control-socket: pure, stdlib-only, no I/O.

Frames are NDJSON, one request line and exactly one response line, correlated by ``id``.
Everything here is codec, constants and the seams the OS legs implement; the supervisor
(``supervisor.py``) owns the idle gate, op dispatch and discovery.

Supervisor entrypoint (pinned; implemented by ``supervisor.py``)::

    run(full_argv: list[str], *, plugin_dir: str, control_base: str) -> int

It returns the child's exit code. ``control_base`` comes from the caller (claude-author.py
resolves the runtime-base rungs once); this package never re-derives them.

OS-leg seam: ``Spawn`` builds a ``Relay`` from the argv of ``build_child_argv`` and the env of
``build_child_env``. A relay never reads ``os.environ`` for the child, so the
CLAUDE_CODE_CHILD_SESSION strip holds on every leg.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Union, runtime_checkable

PROTOCOL_VERSION = 0

OPS = ("prompt", "compact", "model", "effort", "interrupt", "status")
WRITING_OPS = ("prompt", "compact", "model", "effort", "interrupt")
FORCE_OPS = ("prompt", "compact")

ERROR_CODES = ("busy_user", "unknown_op", "bad_args", "not_attested", "pty_dead")

STATES = ("injected", "queued", "deferred_idle")
# deferred_idle is reserved: a closed gate returns busy_user and v0 never emits it.
RESERVED_STATES = ("deferred_idle",)
EMITTED_STATES = ("injected", "queued")

# Bounded question: "can one client exhaust supervisor memory with a line that never ends?"
MAX_FRAME_BYTES = 1024 * 1024

# Bounded question: "has the human pressed a key recently enough that an injection could land
# in a half-typed draft?"
ENV_IDLE_MS = "CLAUDE_AUTHOR_IDLE_MS"
DEFAULT_IDLE_MS = 2000

# Bounded question: "has Esc interrupted the turn before the forced text arrives?"
ENV_FORCE_SETTLE_MS = "CLAUDE_AUTHOR_FORCE_SETTLE_MS"
DEFAULT_FORCE_SETTLE_MS = 300

ALLOWED_ON_BEHALF_OF = ("PM",)

_OP_ARGS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # op -> (required, optional)
    "prompt": (frozenset({"text"}), frozenset({"force"})),
    "compact": (frozenset(), frozenset({"instructions", "force"})),
    "model": (frozenset({"name"}), frozenset()),
    "effort": (frozenset({"level"}), frozenset()),
    "interrupt": (frozenset(), frozenset()),
    "status": (frozenset(), frozenset()),
}

ESC = b"\x1b"
PASTE_START = b"\x1b[200~"
PASTE_END = b"\x1b[201~"
PASTE_MODE_ON = b"\x1b[?2004h"
PASTE_MODE_OFF = b"\x1b[?2004l"
ENTER = b"\r"

RELAY_MARKER_BASE = "[relayed via control-socket"
RELAY_MARKER_PM = " on behalf of PM"

# Discovery layout under <control_base> (= <runtime-base>/coordinator/control-socket/).
CONTROL_BASE_SUBPATH = ("coordinator", "control-socket")
SESSIONS_DIRNAME = "sessions"
SOCK_NAME = "sock"
TURN_FILE = "turn.json"
INSTANCE_HEX_LEN = 12
MAX_SOCK_PATH_BYTES = 103
PIPE_PREFIX = "\\\\.\\pipe\\claude-author-"
DIR_MODE = 0o700
FILE_MODE = 0o600

DISCOVERY_FIELDS = (
    "v", "instance", "session_id", "transport", "address",
    "supervisor_pid", "child_pid", "cwd", "started_at",
)
TURN_FIELDS = ("session_id", "turn_active", "event", "ts")
TURN_EVENTS = ("SessionStart", "UserPromptSubmit", "Stop")
STATUS_FIELDS = (
    "alive", "child_pid", "session_id", "turn_active", "turn_source", "turn_since",
    "user_idle_ms", "draft_dirty", "paste_mode",
)
TRANSPORTS = ("unix", "pipe")


class ProtocolError(Exception):
    """A request the codec rejects; ``code`` is one of ERROR_CODES."""

    def __init__(self, code: str, msg: str, id: Any = None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.id = id


@dataclass(frozen=True)
class Request:
    id: Union[str, int]
    op: str
    args: dict
    on_behalf_of: Optional[str] = None

    @property
    def force(self) -> bool:
        return bool(self.args.get("force", False))


@dataclass(frozen=True)
class ErrorResponse:
    """A failure response; ``close`` tells the transport to drop the connection after sending."""

    id: Any
    code: str
    msg: str
    close: bool = False

    def to_dict(self) -> dict:
        return error_response(self.id, self.code, self.msg)


@dataclass(frozen=True)
class Peer:
    """Transport-attested sender. Fields a transport cannot read stay None."""

    transport: str
    uid: Optional[int] = None
    pid: Optional[int] = None
    sid: Optional[str] = None

    def to_dict(self) -> dict:
        if self.transport == "unix":
            return {"transport": "unix", "uid": self.uid, "pid": self.pid}
        return {"transport": self.transport, "pid": self.pid, "sid": self.sid}


# ---------------------------------------------------------------- responses

def ok_response(id: Any, state: Optional[str] = None, identity: Optional[dict] = None,
                status: Optional[dict] = None) -> dict:
    """Success response. ``state`` is omitted for status, which writes nothing."""
    resp: dict = {"v": PROTOCOL_VERSION, "id": id, "ok": True}
    if state is not None:
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        resp["state"] = state
    resp["identity"] = identity if identity is not None else {}
    if status is not None:
        resp["status"] = status
    return resp


def error_response(id: Any, code: str, msg: str) -> dict:
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code {code!r}")
    return {"v": PROTOCOL_VERSION, "id": id, "ok": False, "error": {"code": code, "msg": msg}}


def encode_response(resp: Union[dict, ErrorResponse]) -> bytes:
    """One NDJSON line (UTF-8, newline-terminated)."""
    if isinstance(resp, ErrorResponse):
        resp = resp.to_dict()
    return json.dumps(resp, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def identity_for(peer: Optional[Peer], on_behalf_of: Optional[str] = None) -> dict:
    """Identity envelope: the transport-stamped sender, plus the client-asserted
    ``on_behalf_of`` echoed as ``relayed``. ``on_behalf_of`` is never attested."""
    ident = peer.to_dict() if peer is not None else {}
    if on_behalf_of is not None:
        ident["on_behalf_of"] = on_behalf_of
        ident["relayed"] = True
    return ident


# ---------------------------------------------------------------- request parsing

def _has_control(s: str, *, allow_newline: bool = False) -> bool:
    for ch in s:
        o = ord(ch)
        if allow_newline and ch in "\n\t":
            continue
        if o < 0x20 or o == 0x7F or 0x80 <= o <= 0x9F:
            return True
    return False


def _bad(msg: str, id: Any = None, *, close: bool = False) -> ErrorResponse:
    return ErrorResponse(id, "bad_args", msg, close)


def _validate_args(op: str, args: dict, id: Any) -> Optional[ErrorResponse]:
    required, optional = _OP_ARGS[op]
    unknown = set(args) - required - optional
    if unknown:
        return _bad(f"unknown args for {op}: {sorted(unknown)}", id)
    missing = required - set(args)
    if missing:
        return _bad(f"missing args for {op}: {sorted(missing)}", id)
    if "force" in args and not isinstance(args["force"], bool):
        return _bad("force must be a boolean", id)
    for key, multiline in (("text", True), ("name", False), ("level", False),
                           ("instructions", False)):
        if key not in args:
            continue
        val = args[key]
        if not isinstance(val, str):
            return _bad(f"{key} must be a string", id)
        if key in ("text", "name", "level") and not val.strip():
            return _bad(f"{key} must not be empty", id)
        if _has_control(val, allow_newline=multiline):
            return _bad(f"{key} contains a control character", id)
    return None


def parse_request(line: Union[bytes, str]) -> Union[Request, ErrorResponse]:
    """Parse and validate one request line; never raises. Failures are ErrorResponse."""
    raw = line.encode("utf-8") if isinstance(line, str) else line
    raw = raw.rstrip(b"\r\n")
    if len(raw) > MAX_FRAME_BYTES:
        return _bad("frame exceeds 1 MiB", close=True)
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _bad("not valid JSON")
    if not isinstance(obj, dict):
        return _bad("frame must be a JSON object")
    if obj.get("v") != PROTOCOL_VERSION or isinstance(obj.get("v"), bool):
        return _bad("unsupported protocol version")
    rid = obj.get("id")
    if isinstance(rid, bool) or not isinstance(rid, (str, int)):
        return _bad("id must be a string or integer")
    op = obj.get("op")
    if not isinstance(op, str) or op not in OPS:
        return ErrorResponse(rid, "unknown_op", f"unknown op {op!r}")
    args = obj.get("args", {})
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _bad("args must be an object", rid)
    obh = obj.get("on_behalf_of")
    if obh is not None and obh not in ALLOWED_ON_BEHALF_OF:
        return _bad(f"on_behalf_of must be one of {list(ALLOWED_ON_BEHALF_OF)} or null", rid)
    err = _validate_args(op, args, rid)
    if err is not None:
        return err
    return Request(id=rid, op=op, args=args, on_behalf_of=obh)


class LineSplitter:
    """Incremental NDJSON framing with the 1 MiB cap; transports feed it raw reads."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Return complete lines (no newline). Raises ProtocolError('bad_args') when a
        line passes MAX_FRAME_BYTES; the transport answers it and closes."""
        self._buf += data
        lines: list[bytes] = []
        while True:
            nl = self._buf.find(b"\n")
            if nl < 0:
                break
            lines.append(bytes(self._buf[:nl]))
            del self._buf[:nl + 1]
            if len(lines[-1]) > MAX_FRAME_BYTES:
                raise ProtocolError("bad_args", "frame exceeds 1 MiB")
        if len(self._buf) > MAX_FRAME_BYTES:
            raise ProtocolError("bad_args", "frame exceeds 1 MiB")
        return lines


Handler = Callable[[Request, Peer], dict]


def handle_line(line: bytes, peer: Optional[Peer], handler: Handler) -> tuple[bytes, bool]:
    """Shared transport step: parse, refuse an unattested peer, dispatch, encode.

    Returns (response line, close_connection). ``peer`` None means attestation failed or
    could not read credentials: every request gets not_attested."""
    parsed = parse_request(line)
    if isinstance(parsed, ErrorResponse):
        return encode_response(parsed), parsed.close
    if peer is None:
        return encode_response(
            ErrorResponse(parsed.id, "not_attested", "peer credentials not attested")), False
    try:
        resp = handler(parsed, peer)
    except ProtocolError as e:
        resp = error_response(parsed.id, e.code, e.msg)
    return encode_response(resp), False


# ---------------------------------------------------------------- keystroke encoding

def render_relayed(text: str, on_behalf_of: Optional[str] = None) -> str:
    """Prefix socket-injected prompt text with the fixed relay marker, so a model reading the
    transcript can never take it for the PM's typed words."""
    marker = RELAY_MARKER_BASE + (RELAY_MARKER_PM if on_behalf_of == "PM" else "") + "] "
    return marker + text


def encode_op(op: str, args: dict, paste_mode: bool, *, on_behalf_of: Optional[str] = None,
              relayed: bool = True) -> bytes:
    """Keystroke bytes for one op's delivery (the force Esc prefix is FORCE_PREFIX).

    prompt: bracketed paste when the child enabled DECSET 2004, then CR; without paste mode,
    multi-line text is bad_args. Prompt text carries the relay marker unless ``relayed`` is
    False. status writes nothing and encodes to b""."""
    if op not in OPS:
        raise ProtocolError("unknown_op", f"unknown op {op!r}")
    err = _validate_args(op, args, None)
    if err is not None:
        raise ProtocolError(err.code, err.msg)
    if op == "status":
        return b""
    if op == "interrupt":
        return ESC
    if op == "compact":
        instr = args.get("instructions")
        body = "/compact" + (f" {instr}" if instr else "")
        return body.encode("utf-8") + ENTER
    if op == "model":
        return f"/model {args['name']}".encode("utf-8") + ENTER
    if op == "effort":
        return f"/effort {args['level']}".encode("utf-8") + ENTER
    text = args["text"]
    if relayed:
        text = render_relayed(text, on_behalf_of)
    if paste_mode:
        return PASTE_START + text.encode("utf-8") + PASTE_END + ENTER
    if "\n" in text:
        raise ProtocolError("bad_args", "multi-line prompt requires the child's paste mode")
    return text.encode("utf-8") + ENTER


FORCE_PREFIX = ESC


# ---------------------------------------------------------------- turn / discovery shapes

def turn_record(session_id: Optional[str], turn_active: bool, event: str, ts: float) -> dict:
    """The turn.json shape the turn hook writes and the supervisor reads."""
    return {"session_id": session_id, "turn_active": turn_active, "event": event, "ts": ts}


def discovery_record(*, instance: str, session_id: Optional[str], transport: str, address: str,
                     supervisor_pid: int, child_pid: Optional[int], cwd: str,
                     started_at: str) -> dict:
    return {
        "v": PROTOCOL_VERSION, "instance": instance, "session_id": session_id,
        "transport": transport, "address": address, "supervisor_pid": supervisor_pid,
        "child_pid": child_pid, "cwd": cwd, "started_at": started_at,
    }


def is_instance_id(value: str) -> bool:
    return bool(re.fullmatch(rf"[0-9a-f]{{{INSTANCE_HEX_LEN}}}", value))


def pipe_address(instance: str) -> str:
    return PIPE_PREFIX + instance


# ---------------------------------------------------------------- OS-leg seams

@runtime_checkable
class Observers(Protocol):
    """Fed by the relay: every human input byte, every child output byte."""

    def on_input(self, data: bytes) -> None: ...

    def on_output(self, data: bytes) -> None: ...


@runtime_checkable
class Relay(Protocol):
    def write(self, data: bytes) -> None: ...

    def resize(self, cols: int, rows: int) -> None: ...

    def alive(self) -> bool: ...

    def wait(self) -> int: ...


@runtime_checkable
class Transport(Protocol):
    address: str

    def serve(self, handler: Handler) -> None: ...

    def close(self) -> None: ...


class Spawn(Protocol):
    def __call__(self, argv: list[str], env: dict[str, str], observers: Observers) -> Relay: ...
