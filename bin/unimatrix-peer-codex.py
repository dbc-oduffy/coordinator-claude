#!/usr/bin/env python3
"""Codex adapter for the unimatrix peer router: one user turn into a live Codex thread.

Speaks the Codex app-server control protocol (JSON-RPC text frames over a WebSocket on a unix
socket) with a minimal stdlib RFC 6455 client, so the vendored script carries no third-party
dependency. Socket path: $CODEX_APP_SERVER_SOCK, else ~/.codex/app-server-control/app-server-control.sock.
"""
import asyncio
import base64
import importlib.util
import json
import os
import platform
import struct
import subprocess
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

TURN_TIMEOUT = 600
NO_REPLY = "[unimatrix-peer-codex] no reply before timeout"
STRANDED = "[unimatrix-peer-codex] queued item stranded"
STRAND_GRACE_SECONDS = 30  # a drained queue starts the next item at once; this long after a turn ends, it was dropped
TURN_BOUNDARY_EVENTS = ("task_complete", "turn_complete", "turn_aborted")
RECORDED_BINARY = "codex-binary.path"
FACE_PRIME = "Reply with the single word READY. Do not use tools."
DEFAULT_SOCK = "~/.codex/app-server-control/app-server-control.sock"


def socket_path():
    """Control socket path: env override first, else the Codex default."""
    return os.environ.get("CODEX_APP_SERVER_SOCK") or os.path.expanduser(DEFAULT_SOCK)


class WsClient:
    """Text-frame WebSocket client over an asyncio stream pair (client frames are masked)."""

    def __init__(self, reader, writer) -> None:
        self.reader = reader
        self.writer = writer
        self.proc = None
        self.rid = 0

    async def call(self, method, params, timeout=TURN_TIMEOUT) -> dict:
        """One JSON-RPC request; returns its result, raises RuntimeError on an error reply."""
        self.rid += 1
        await self.send(json.dumps({"id": self.rid, "method": method, "params": params}))
        while True:
            msg = json.loads(await asyncio.wait_for(self.recv(), timeout=timeout))
            if msg.get("id") == self.rid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]

    @classmethod
    async def connect(cls, sock, host="localhost", path="/") -> "WsClient":
        if not hasattr(asyncio, "open_unix_connection"):
            raise OSError("unix sockets are unavailable on this platform")
        reader, writer = await asyncio.open_unix_connection(sock)
        return await cls._upgrade(reader, writer, host, path)

    @classmethod
    async def _upgrade(cls, reader, writer, host, path) -> "WsClient":
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                      "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            writer.close()
            raise RuntimeError(f"websocket upgrade refused: {status.decode(errors='replace')}")
        return cls(reader, writer)

    async def _send(self, opcode, payload):
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
        elif n < 65536:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.writer.write(head + mask + masked)
        await self.writer.drain()

    async def send(self, text):
        await self._send(0x1, text.encode())

    async def _frame(self):
        b0, b1 = await self.reader.readexactly(2)
        n = b1 & 0x7F
        if n == 126:
            (n,) = struct.unpack("!H", await self.reader.readexactly(2))
        elif n == 127:
            (n,) = struct.unpack("!Q", await self.reader.readexactly(8))
        mask = await self.reader.readexactly(4) if b1 & 0x80 else None
        data = await self.reader.readexactly(n)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return b0 & 0x80, b0 & 0x0F, data

    async def recv(self):
        """Next complete text message; answers pings, raises ConnectionError on close."""
        buf = b""
        while True:
            try:
                fin, op, data = await self._frame()
            except asyncio.IncompleteReadError as e:
                raise ConnectionError("websocket closed") from e
            if op == 0x8:
                raise ConnectionError("websocket closed by peer")
            if op == 0x9:
                await self._send(0xA, data)
                continue
            if op == 0xA:
                continue
            buf += data
            if fin:
                return buf.decode()

    async def close(self) -> None:
        try:
            await self._send(0x8, b"")
        except (ConnectionError, OSError):
            pass
        self.writer.close()
        if self.proc is not None:
            if self.proc.returncode is None:
                self.proc.kill()
            await self.proc.wait()


class StdioClient(WsClient):
    """JSON-RPC over a windowless `codex app-server --stdio` child (newline-delimited, no daemon, no socket).

    The child owns the thread's face for as long as it lives; close() kills it.
    """

    @classmethod
    async def spawn(cls, cwd=None) -> "StdioClient":
        proc = await asyncio.create_subprocess_exec(
            codex_binary(), "app-server", "--stdio", env=exec_env(), cwd=cwd,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        client = cls(proc.stdout, proc.stdin)
        client.proc = proc
        return client

    async def send(self, text) -> None:
        self.writer.write(text.encode() + b"\n")
        await self.writer.drain()

    async def recv(self) -> str:
        """Next non-blank stdout line; raises ConnectionError when the child's stdout closes."""
        while True:
            line = await self.reader.readline()
            if not line:
                raise ConnectionError("app-server stdio closed")
            if line.strip():
                return line.decode()

    async def close(self) -> None:
        try:
            self.writer.close()
        except OSError:
            pass
        if self.proc.returncode is None:
            self.proc.kill()
        await self.proc.wait()
        transport = getattr(self.reader, "_transport", None)  # Closes the stdout pipe the proactor loop would warn about at exit.
        if transport is not None:
            transport.close()


def codex_home():
    """Codex state dir: $CODEX_HOME, else ~/.codex."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def recorded_binary_file(registry_dir=None):
    """Where the SessionStart hook records the absolute codex path: <settings home>/host-sessions/codex/codex-binary.path."""
    if registry_dir is None:
        spec = importlib.util.spec_from_file_location("unimatrix_roster_for_codex", Path(__file__).resolve().parent / "unimatrix-roster.py")
        roster = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(roster)
        registry_dir = roster.delivery_settings_home() / "host-sessions" / "codex"
    return Path(registry_dir) / RECORDED_BINARY


def recorded_binary(registry_dir=None):
    """The absolute codex path the SessionStart hook recorded, or None when absent, unreadable or no longer a file."""
    try:
        text = recorded_binary_file(registry_dir).read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return text if text and os.path.isabs(text) and os.path.isfile(text) else None


def record_binary(registry_dir=None):
    """Write shutil.which("codex") (absolute only) to the record when it differs; return the path or None."""
    found = shutil.which("codex")
    if not found or not os.path.isabs(found):
        return None
    target = recorded_binary_file(registry_dir)
    try:
        if target.read_text(encoding="utf-8").strip() == found:
            return found
    except OSError:
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp.write_text(found + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return found


def codex_binary():
    """Resolve codex: CODEX_BIN, then PATH, then the hook-recorded absolute path, then bare "codex".

    npm wrappers are swapped for their package's native executable."""
    configured = os.environ.get("CODEX_BIN")
    found = shutil.which(configured or "codex") or configured or recorded_binary() or "codex"
    resolved = Path(found).resolve()
    windows_wrapper = sys.platform == "win32" and Path(found).suffix.lower() in (".cmd", ".ps1", ".bat")
    if windows_wrapper:
        root = Path(found).parent / "node_modules" / "@openai" / "codex"
    elif resolved.name == "codex.js" and resolved.parent.name == "bin" and resolved.parent.parent.name == "codex":
        root = resolved.parent.parent
    else:
        return found
    arch = {"arm64": "aarch64", "aarch64": "aarch64", "amd64": "x86_64", "x86_64": "x86_64"}.get(platform.machine().lower())
    suffix = {"darwin": "apple-darwin", "linux": "unknown-linux-musl", "win32": "pc-windows-msvc"}.get(sys.platform)
    if arch and suffix:
        triple = f"{arch}-{suffix}"
        package_arch = "arm64" if arch == "aarch64" else "x64"
        executable = "codex.exe" if sys.platform == "win32" else "codex"
        candidates = [root / "vendor" / triple / "bin" / executable]
        candidates += [root / "node_modules" / "@openai" / f"codex-{sys.platform}-{package_arch}" / "vendor" / triple / "bin" / executable]
        candidates += [root.parent / f"codex-{sys.platform}-{package_arch}" / "vendor" / triple / "bin" / executable]
        candidates = [p for p in candidates if p.is_file()]
        if len(candidates) != 1:
            raise RuntimeError(f"missing or ambiguous native Codex in {root}; repair the npm installation or set CODEX_BIN to the native executable")
        if sys.platform != "win32" and not os.access(candidates[0], os.X_OK):
            raise RuntimeError(f"native Codex is not executable: {candidates[0]}; repair the npm installation or set CODEX_BIN to the native executable")
        return str(candidates[0])
    raise RuntimeError("unsupported Codex package platform; set CODEX_BIN to the native executable")


def rollout_path(thread_id, home=None):
    """Newest rollout jsonl of the thread under (home or codex_home())/sessions, or None before it exists."""
    found = sorted((Path(home) if home else codex_home()).joinpath("sessions").glob(f"**/rollout-*{thread_id}.jsonl"))
    return found[-1] if found else None


def rollout_index(home=None):
    """thread id -> newest rollout jsonl, from one walk of (home or codex_home())/sessions.

    A rollout is named rollout-<timestamp>-<36-char thread id>.jsonl.
    """
    out = {}
    for path in sorted((Path(home) if home else codex_home()).joinpath("sessions").glob("**/rollout-*.jsonl")):
        out[path.stem[-36:]] = path
    return out


def thread_addressable(thread_id, home=None, index=None):
    """True when the thread has a rollout whose first session_meta does not mark it a sub-agent.

    Reads only the first rollout line. `index` is a rollout_index() result, so a caller
    checking many threads walks the sessions tree once.
    """
    path = index.get(thread_id) if index is not None else rollout_path(thread_id, home)
    if path is None:
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            row = json.loads(fh.readline())
    except (OSError, ValueError):
        return False
    payload = row.get("payload") if isinstance(row, dict) and row.get("type") == "session_meta" else None
    source = payload.get("source") if isinstance(payload, dict) else None
    return not (source == "subagent" or (isinstance(source, dict) and "subagent" in source))


def rollout_rows(path):
    """Parsed rows of the rollout; a torn trailing line (writer mid-append) is skipped."""
    if path is None:
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def assistant_text(row):
    """Final assistant message text of a rollout row, else None."""
    p = row.get("payload") or {}
    if row.get("type") != "response_item" or p.get("type") != "message" or p.get("role") != "assistant":
        return None
    if p.get("phase") not in (None, "final_answer"):
        return None
    text = "".join(c.get("text", "") for c in p.get("content", []) if c.get("type") == "output_text")
    return text or None


def user_text(row):
    """Text of a user message rollout row, else None."""
    p = row.get("payload") or {}
    if row.get("type") != "response_item" or p.get("type") != "message" or p.get("role") != "user":
        return None
    return "".join(c.get("text", "") for c in p.get("content", []) if c.get("type") == "input_text") or None


class RolloutTail:
    """Read bounded newly appended bytes only; changed generations fail closed."""

    CHUNK_BYTES = 64 * 1024
    MAX_LINE_BYTES = 1024 * 1024
    MAX_POLL_BYTES = 1024 * 1024

    def __init__(self, thread_id):
        self.thread_id = thread_id
        self.path = rollout_path(thread_id)
        self.offset = 0
        self.identity = None
        self.partial = b""
        if self.path is None:
            raise ValueError("no pre-enqueue rollout baseline")
        with self.path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            self.identity = (info.st_dev, info.st_ino)
            self.offset = stream.seek(0, os.SEEK_END)

    def rows(self):
        path = self.path  # Discover once; never rescan all session filenames per poll.
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            identity = (info.st_dev, info.st_ino)
            if identity != self.identity or info.st_size < self.offset:
                raise ValueError("rollout replaced or truncated")
            stream.seek(self.offset)
            remaining = min(info.st_size - self.offset, self.MAX_POLL_BYTES)
            while remaining:
                data = stream.read(min(self.CHUNK_BYTES, remaining))
                if not data:
                    raise ValueError("rollout changed during tail read")
                remaining -= len(data)
                self.offset += len(data)
                pieces = (self.partial + data).split(b"\n")
                self.partial = pieces.pop()
                if len(self.partial) > self.MAX_LINE_BYTES:
                    raise ValueError("rollout line exceeds tail bound")
                for line in pieces:
                    if len(line) > self.MAX_LINE_BYTES:
                        raise ValueError("rollout line exceeds tail bound")
                    try:
                        row = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue  # Same malformed-complete-line tolerance as rollout_rows.
                    if isinstance(row, dict):
                        yield row
            after = os.fstat(stream.fileno())
            current = path.stat()
            if ((after.st_dev, after.st_ino) != self.identity or after.st_size < self.offset
                    or (current.st_dev, current.st_ino) != self.identity or current.st_size < self.offset):
                raise ValueError("rollout changed during tail read")


class QueueFailed(RuntimeError):
    """`codex queue` exited non-zero: no live app-server took the message, so nothing was enqueued."""


def exec_env() -> dict:
    """Child env for a headless exec; on Windows the WindowsApps alias stubs are stripped from PATH
    with codex-exec-windows.py's own clean_path."""
    env = dict(os.environ)
    if os.name == "nt":
        spec = importlib.util.spec_from_file_location(
            "codex_exec_windows_for_peer", Path(__file__).resolve().parent / "codex-exec-windows.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        env["PATH"] = mod.clean_path(env.get("PATH", ""))
    return env


async def exec_turn(thread_id, text, timeout=TURN_TIMEOUT) -> str:
    """Headless one-shot turn: exactly one `codex exec` spawn, final agent message returned.

    Resumes the thread when its rollout exists, else runs a fresh one-shot. The prompt goes on
    stdin and the reply is read from --output-last-message. A timeout returns NO_REPLY; a
    non-zero exit raises RuntimeError.
    """
    resume = not thread_id.startswith("-") and rollout_path(thread_id) is not None
    with tempfile.TemporaryDirectory(prefix="unimatrix-codex-exec-") as scratch:
        out = Path(scratch) / "last-message.txt"
        argv = [codex_binary(), "exec"] + (["resume"] if resume else []) + [
            "--skip-git-repo-check", "-o", str(out)] + ([thread_id] if resume else []) + ["-"]
        try:
            proc = await asyncio.to_thread(
                subprocess.run, argv, input=text, capture_output=True, text=True, encoding="utf-8",
                timeout=timeout, env=exec_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            return NO_REPLY
        if proc.returncode != 0:
            raise RuntimeError(f"codex exec failed ({proc.returncode}): {(proc.stderr or '').strip()}")
        try:
            return out.read_text(encoding="utf-8").strip() or NO_REPLY
        except OSError:
            return NO_REPLY


def is_turn_boundary(row) -> bool:
    """True for a rollout event row that ends a Codex turn (completed or aborted)."""
    p = row.get("payload") or {}
    return row.get("type") == "event_msg" and p.get("type") in TURN_BOUNDARY_EVENTS


async def queue_turn(thread_id, text, timeout=TURN_TIMEOUT, interval=1.0, on_queued=None, on_echoed=None) -> str:
    """Queue `text` onto a thread whose TUI holds it (`codex queue`), then read the reply from the rollout.

    Seeks the rollout EOF first, waits for the queued message to appear as a user row,
    and returns the first final assistant message after that row (so a turn already in flight
    when the message was queued is not mistaken for the reply), or NO_REPLY once `timeout`
    seconds pass. `on_queued` is called once the enqueue succeeds, before the reply wait, so a
    caller serializing per thread can release its lock and let the next message enqueue.
    `on_echoed` is called once when the queued text's user row appears. STRANDED is returned when
    a turn boundary passed, no turn has started since, and STRAND_GRACE_SECONDS elapsed without
    the echo: the item never started, so the caller may enqueue it again.
    """
    try:
        tail = RolloutTail(thread_id)
    except (OSError, ValueError):
        tail = None  # Observation failure must never suppress the requested enqueue.
    proc = await asyncio.to_thread(
        subprocess.run, [codex_binary(), "--remote", "unix://", "queue", "--thread", thread_id, "--message", text],
        capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        raise QueueFailed(f"codex queue failed ({proc.returncode}): {proc.stderr.strip()}")
    if on_queued is not None:
        on_queued()
    if tail is None:
        return NO_REPLY  # Enqueued once, but no trustworthy pre-enqueue baseline.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    echoed = False
    boundary_at = None  # when the last turn boundary was seen with no turn started since
    while True:
        try:
            # Finish generation checks before accepting any reply from this bounded batch.
            for r in list(tail.rows()):
                if not echoed:
                    echoed = text in (user_text(r) or "")
                    if echoed:
                        if on_echoed is not None:
                            on_echoed()
                    elif user_text(r):
                        boundary_at = None  # another turn started: wait for its boundary
                    elif is_turn_boundary(r):
                        boundary_at = loop.time()
                    continue
                reply = assistant_text(r)
                if reply:
                    return reply
        except (OSError, ValueError):
            return NO_REPLY
        if not echoed and boundary_at is not None and loop.time() - boundary_at >= STRAND_GRACE_SECONDS:
            return STRANDED
        if loop.time() >= deadline:
            return NO_REPLY
        await asyncio.sleep(interval)


def appended_rows(path, offset):
    """Complete JSONL rows after a byte offset; retain a torn tail for the next read.

    Polling reads only newly appended bytes, never a growing thread's entire history.
    """
    if path is None:
        return [], offset
    try:
        with path.open("rb") as file:
            if file.seek(0, 2) < offset:
                offset = 0
            file.seek(offset)
            data = file.read()
    except OSError:
        return [], offset
    complete, separator, _ = data.rpartition(b"\n")
    if not separator:
        return [], offset
    rows = []
    for line in complete.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows, offset + len(complete) + 1


async def turn_reply(ws, thread_id, text, timeout) -> str:
    """turn/start on an initialized client, then the agent's final text from its stream."""
    await ws.call("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": text}]}, timeout)
    deltas, final = [], ""
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        m, p = msg.get("method", ""), msg.get("params", {})
        if m == "item/agentMessage/delta":
            deltas.append(p.get("delta", ""))
        elif m == "item/completed" and p.get("item", {}).get("type") == "agentMessage":
            final = p["item"].get("text", "") or final
        elif m == "turn/completed":
            return final or "".join(deltas)


async def stdio_turn(thread_id, text, timeout=TURN_TIMEOUT) -> str:
    """Windowless headless turn on its own `codex app-server --stdio` child, which registers the thread as a face while it runs.

    Resumes the thread when its rollout exists, else starts a fresh thread. Returns the agent's text.
    """
    ws = await StdioClient.spawn()
    try:
        await ws.call("initialize", {"clientInfo": {"name": "claude_bridge", "version": "0.1.0"}}, timeout)
        await ws.send(json.dumps({"method": "initialized"}))
        if not thread_id.startswith("-") and rollout_path(thread_id) is not None:
            await ws.call("thread/resume", {"threadId": thread_id, "excludeTurns": True}, timeout)
        else:
            thread_id = (await ws.call("thread/start", {}, timeout))["thread"]["id"]
        try:
            register_face(thread_id, ws.proc.pid)
        except (RuntimeError, ValueError, OSError):
            pass  # An unbound thread still gets its reply; only the face is missing.
        return await turn_reply(ws, thread_id, text, timeout)
    finally:
        await ws.close()


async def queue_or_exec(thread_id, text, timeout, on_queued=None, on_echoed=None) -> str:
    """Queue onto a live app-server; when `codex queue` is refused (nothing enqueued), run a headless turn.

    On win32 the headless turn is stdio_turn (registers a face); elsewhere a `codex exec` one-shot.
    """
    try:
        return await queue_turn(thread_id, text, timeout, on_queued=on_queued, on_echoed=on_echoed)
    except QueueFailed:
        if sys.platform == "win32":
            return await stdio_turn(thread_id, text, timeout)
        return await exec_turn(thread_id, text, timeout)


async def codex_turn(sock, thread_id, text, timeout=TURN_TIMEOUT, tui_held=False, on_queued=None,
                     on_echoed=None) -> str:
    """One user turn into the live thread; returns the agent's text.

    A thread a TUI holds (`tui_held`) is always queued with `codex queue` and read from the
    rollout. Otherwise the turn goes through the app-server socket, falling back to the queue
    when the socket is absent or unconnectable, and to a headless `codex exec` one-shot
    (`exec_turn`) when the queue finds no live app-server either.
    `timeout` bounds each wait for the next server message, not the whole turn.
    """
    if tui_held:
        return await queue_turn(thread_id, text, timeout, on_queued=on_queued, on_echoed=on_echoed)
    if sys.platform == "win32":
        return await queue_or_exec(thread_id, text, timeout, on_queued=on_queued, on_echoed=on_echoed)
    try:
        ws = await WsClient.connect(sock)
    except OSError:
        return await queue_or_exec(thread_id, text, timeout, on_echoed=on_echoed)
    try:
        rid = 0

        async def call(method, params):
            nonlocal rid
            rid += 1
            await ws.send(json.dumps({"id": rid, "method": method, "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                if msg.get("id") == rid:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg["result"]

        await call("initialize", {"clientInfo": {"name": "claude_bridge", "version": "0.1.0"}})
        await ws.send(json.dumps({"method": "initialized"}))
        await call("thread/resume", {"threadId": thread_id, "excludeTurns": True})
        return await turn_reply(ws, thread_id, text, timeout)
    finally:
        await ws.close()


def _sibling(name) -> "ModuleType":
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_for_peer", Path(__file__).resolve().parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def register_face(thread_id, holder_pid, peers_file=None, registry_dir=None) -> str:
    """Upsert the thread into peers.json as a Codex face held by `holder_pid`; returns "added", "rebound" or "present".

    The row carries the engine-owned address and the holder, so the router lists the face while
    that process lives and marks it stale when it dies. Raises RuntimeError when the engine has bound
    no address to the thread.
    """
    hook = _sibling("unimatrix-codex-hook-sessionstart")
    if peers_file is None:
        peers_file = _sibling("unimatrix-peer-router").default_peers_file()
    if registry_dir is None:
        registry_dir = _sibling("unimatrix-roster").delivery_settings_home() / "host-sessions" / "codex"
    address = _sibling("unimatrix-peer-contract").read_codex_address(registry_dir, thread_id, socket.gethostname())
    if not address:
        raise RuntimeError(f"codex thread {thread_id} is unbound: no engine address")
    return hook.register_peer(peers_file, address["name"], "codex", thread_id, address=address,
                              holder=hook.codex_holder(holder_pid))


async def start_thread(sock, timeout=30, cwd=None, on_ready=None, hold=False) -> str:
    """Create a thread on the running app-server daemon (initialize, thread/start, one priming turn); returns its id.

    Never spawns a daemon: an absent socket raises. Windows Python has no unix sockets and the
    daemon proxy resets, so there the thread lives on a windowless `codex app-server --stdio` child
    that is registered as the face's holder; with `hold` the child is kept alive after `on_ready(thread_id)`
    until this task is cancelled, because the face is live only while its holder is.
    """
    try:
        ws = await (StdioClient.spawn(cwd) if sys.platform == "win32" else WsClient.connect(sock))
    except (asyncio.IncompleteReadError, OSError) as e:
        raise RuntimeError(f"app-server daemon not reachable at {sock}") from e
    try:
        await ws.call("initialize", {"clientInfo": {"name": "claude_bridge", "version": "0.1.0"}}, timeout)
        await ws.send(json.dumps({"method": "initialized"}))
        thread_id = (await ws.call("thread/start", {"cwd": cwd} if cwd else {}, timeout))["thread"]["id"]
        # A thread is a router face only once its rollout and state row exist, which the first turn writes.
        await ws.call("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": FACE_PRIME}]}, timeout)
        while json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout)).get("method") != "turn/completed":
            pass
        if ws.proc is not None:
            register_face(thread_id, ws.proc.pid)
        if on_ready:
            on_ready(thread_id)
        if hold and ws.proc is not None:
            await asyncio.Event().wait()
        return thread_id
    finally:
        await ws.close()


def main(argv=None) -> int:
    """`unimatrix-peer-codex.py <thread-id> <text>`: one turn into the thread; prints the reply.

    `unimatrix-peer-codex.py --start-face [cwd]`: start a thread on the daemon socket; prints its id.
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["--start-face"] and len(argv) <= 2:
        try:
            asyncio.run(start_thread(socket_path(), cwd=argv[1] if len(argv) == 2 else None,
                                     on_ready=lambda tid: print(tid, flush=True), hold=True))
        except KeyboardInterrupt:
            pass
        return 0
    if len(argv) != 2:
        sys.exit("usage: unimatrix-peer-codex.py <thread-id> <text> | --start-face [cwd]")
    print(asyncio.run(codex_turn(socket_path(), argv[0], argv[1])))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-peer-codex [-h]\nunimatrix Codex peer")
        raise SystemExit(0)
    sys.exit(main())
