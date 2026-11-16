#!/usr/bin/env python3
"""Codex adapter for the unimatrix peer router: one user turn into a live Codex thread.

Speaks the Codex app-server control protocol (JSON-RPC text frames over a WebSocket on a unix
socket) with a minimal stdlib RFC 6455 client, so the vendored script carries no third-party
dependency. Socket path: $CODEX_APP_SERVER_SOCK, else ~/.codex/app-server-control/app-server-control.sock.
"""
import asyncio
import base64
import json
import os
import struct
import subprocess
import shutil
import sys
from pathlib import Path

TURN_TIMEOUT = 600
NO_REPLY = "[unimatrix-peer-codex] no reply before timeout"
DEFAULT_SOCK = "~/.codex/app-server-control/app-server-control.sock"


def socket_path():
    """Control socket path: env override first, else the Codex default."""
    return os.environ.get("CODEX_APP_SERVER_SOCK") or os.path.expanduser(DEFAULT_SOCK)


class WsClient:
    """Text-frame WebSocket client over an asyncio stream pair (client frames are masked)."""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(cls, sock, host="localhost", path="/"):
        if not hasattr(asyncio, "open_unix_connection"):
            raise OSError("unix sockets are unavailable on this platform")
        reader, writer = await asyncio.open_unix_connection(sock)
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

    async def close(self):
        try:
            await self._send(0x8, b"")
        except (ConnectionError, OSError):
            pass
        self.writer.close()


def codex_home():
    """Codex state dir: $CODEX_HOME, else ~/.codex."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def codex_binary():
    """Resolve the native Windows executable, avoiding npm's shell wrapper for message text."""
    configured = os.environ.get("CODEX_BIN")
    found = shutil.which(configured or "codex") or configured or "codex"
    if os.name == "nt" and Path(found).suffix.lower() in (".cmd", ".ps1", ".bat"):
        root = Path(found).parent / "node_modules" / "@openai" / "codex"
        candidates = sorted(root.glob("node_modules/@openai/codex-win32-*/vendor/*/*/codex.exe"))
        if len(candidates) != 1:
            raise RuntimeError("set CODEX_BIN to the native codex.exe path")
        return str(candidates[0])
    return found


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


async def queue_turn(thread_id, text, timeout=TURN_TIMEOUT, interval=1.0):
    """Queue `text` onto a thread whose TUI holds it (`codex queue`), then read the reply from the rollout.

    Seeks the rollout EOF first, waits for the queued message to appear as a user row,
    and returns the first final assistant message after that row (so a turn already in flight
    when the message was queued is not mistaken for the reply), or NO_REPLY once `timeout`
    seconds pass.
    """
    try:
        tail = RolloutTail(thread_id)
    except (OSError, ValueError):
        tail = None  # Observation failure must never suppress the requested enqueue.
    proc = await asyncio.to_thread(
        subprocess.run, [codex_binary(), "--remote", "unix://", "queue", "--thread", thread_id, "--message", text],
        capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0:
        raise RuntimeError(f"codex queue failed ({proc.returncode}): {proc.stderr.strip()}")
    if tail is None:
        return NO_REPLY  # Enqueued once, but no trustworthy pre-enqueue baseline.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    echoed = False
    while True:
        try:
            # Finish generation checks before accepting any reply from this bounded batch.
            for r in list(tail.rows()):
                if not echoed:
                    echoed = text in (user_text(r) or "")
                    continue
                reply = assistant_text(r)
                if reply:
                    return reply
        except (OSError, ValueError):
            return NO_REPLY
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


async def codex_turn(sock, thread_id, text, timeout=TURN_TIMEOUT, tui_held=False):
    """One user turn into the live thread; returns the agent's text.

    A thread a TUI holds (`tui_held`) is always queued with `codex queue` and read from the
    rollout. Otherwise the turn goes through the app-server socket, falling back to the queue
    when the socket is absent or unconnectable.
    `timeout` bounds each wait for the next server message, not the whole turn.
    """
    if tui_held or sys.platform == "win32":
        return await queue_turn(thread_id, text, timeout)
    try:
        ws = await WsClient.connect(sock)
    except OSError:
        return await queue_turn(thread_id, text, timeout)
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
        await call("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": text}]})
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
    finally:
        await ws.close()


def main(argv=None):
    """`unimatrix-peer-codex.py <thread-id> <text>`: one turn into the thread; prints the reply."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 2:
        sys.exit("usage: unimatrix-peer-codex.py <thread-id> <text>")
    print(asyncio.run(codex_turn(socket_path(), argv[0], argv[1])))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-peer-codex [-h]\nunimatrix Codex peer")
        raise SystemExit(0)
    sys.exit(main())
