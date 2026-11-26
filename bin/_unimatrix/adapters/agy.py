"""Agy (Antigravity) host adapter for Unimatrix."""
import asyncio
import uuid
import json
import os
import socket
import sys
import threading
from pathlib import Path

from _unimatrix import proc as _proc
from _unimatrix import transport as _transport

BRAIN_ENV = "AGY_BRAIN_DIR"
NO_REPLY = "[unimatrix-peer-agy] no final agy reply within timeout"
_TRANSCRIPT_TAIL = Path(".system_generated") / "logs" / "transcript_full.jsonl"
NO_LEG = ("[unimatrix-peer-agy] not delivered: this agy conversation has no leg endpoint. The SessionStart "
          "hook normally starts it; if this session predates the hook, ask the agy user to let it run any "
          "shell command (run_command), then resend.")
QUEUED = ("[unimatrix-peer-agy] queued: the agy leg is not live; the message is spooled and delivered at "
          "the agy session's next turn. No reply is awaited.")


def own_session(env=None) -> str | None:
    environ = os.environ if env is None else env
    return environ.get("ANTIGRAVITY_CONVERSATION_ID") or None


def brain_dir() -> Path:
    """Which transcript root applies: $AGY_BRAIN_DIR else ~/.gemini/antigravity-cli/brain."""
    return Path(os.environ.get(BRAIN_ENV) or Path.home() / ".gemini" / "antigravity-cli" / "brain")


def transcript_path(conversation_id) -> Path:
    """Where a conversation's transcript lives under the brain root."""
    return brain_dir() / conversation_id / _TRANSCRIPT_TAIL


def rows(path) -> list[dict]:
    """Parsed transcript rows, [] while the transcript does not exist yet."""
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def _pipe_roundtrip(leg_sock, text):
    with open(leg_sock, "r+b", buffering=0) as pipe:
        pipe.write((json.dumps({"text": text}) + "\n").encode())
        return json.loads(pipe.readline() or b'{"ok":false,"body":"leg closed"}')


def to_leg(leg_sock, text, timeout=40):
    """Send one JSON line to the leg and return its one-line JSON answer."""
    if sys.platform == "win32" and str(leg_sock).startswith("\\\\"):
        box = {}

        def run():
            try:
                box["r"] = _pipe_roundtrip(leg_sock, text)
            except Exception as e:
                box["r"] = {"ok": False, "body": f"leg error: {e}"}

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout)
        return box.get("r", {"ok": False, "body": "leg timed out"})
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    try:
        s.connect(str(leg_sock))
        s.sendall((json.dumps({"text": text}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    return json.loads(buf or b'{"ok":false,"body":"leg closed"}')


async def await_reply(path, baseline, timeout=600, interval=1.0):
    """First final model message (content, no tool calls) appended after `baseline` rows."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        for r in rows(path)[baseline:]:
            if (r.get("source") == "MODEL" and r.get("type") == "PLANNER_RESPONSE"
                    and r.get("content") and not r.get("tool_calls")):
                return r["content"]
        if loop.time() >= deadline:
            return NO_REPLY
        await asyncio.sleep(interval)


async def agy_turn(leg_sock, tpath, text, timeout=600, interval=1.0, sender=None, wait_reply=True):
    """What did agy answer to `text`: baseline the transcript, deliver via the leg, return the reply.

    When `wait_reply` is False (peer-to-peer send where the receiver replies asynchronously via
    unimatrix-send.py), return a written receipt as soon as the leg accepts the message so two peers
    cannot deadlock waiting on each other's turn to end.
    """
    baseline = len(rows(tpath)) if wait_reply else 0
    try:
        ack = await asyncio.to_thread(sender or to_leg, leg_sock, text)
    except (FileNotFoundError, ConnectionRefusedError):
        return NO_LEG
    if not ack.get("ok"):
        return f"[unimatrix-peer-agy] delivery failed: {ack}"
    if ack.get("queued"):
        return QUEUED
    if not wait_reply:
        return {"written": True, "msg_id": str(uuid.uuid4())}
    return await await_reply(tpath, baseline, timeout, interval)


class AgyAdapter:
    vendor = "agy"

    def own_session(self, env=None) -> str | None:
        return own_session(env)

    def discover_peers(self, **kwargs) -> list[dict]:
        return []

    async def deliver(self, peer: dict, text: str, leg_endpoint_fn=None, timeout=600, interval=1.0) -> str:
        target = peer["target"]
        ep = leg_endpoint_fn(target) if leg_endpoint_fn else peer.get("endpoint")
        if not ep:
            return NO_LEG
        return await agy_turn(ep, transcript_path(target), text, timeout=timeout, interval=interval)

    def owned_endpoints(self, state_root=None) -> set[str]:
        if state_root is None:
            return set()
        return _transport.live_owned_endpoints(state_root, _proc.pid_alive)
