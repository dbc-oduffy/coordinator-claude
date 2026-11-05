"""agy peer adapter: deliver one turn to a live agy conversation through its agy-run leg
(unimatrix-agy-leg.py) and read the reply from the conversation transcript.

The leg holds agy's CSRF token; this module never sees it.
"""
import asyncio
import importlib.util
import json
import os
import socket
import sys
import threading
from pathlib import Path

BRAIN_ENV = "AGY_BRAIN_DIR"
NO_REPLY = "[unimatrix-peer-agy] no final agy reply within timeout"
_TRANSCRIPT_TAIL = Path(".system_generated") / "logs" / "transcript_full.jsonl"


def _roster():
    spec = importlib.util.spec_from_file_location(
        "unimatrix_roster", Path(__file__).resolve().with_name("unimatrix-roster.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def brain_dir():
    """Which transcript root applies: $AGY_BRAIN_DIR else ~/.gemini/antigravity-cli/brain."""
    return Path(os.environ.get(BRAIN_ENV) or Path.home() / ".gemini" / "antigravity-cli" / "brain")


def transcript_path(conversation_id):
    """Where a conversation's transcript lives under the brain root."""
    return brain_dir() / conversation_id / _TRANSCRIPT_TAIL


def leg_endpoint(conversation_id, platform=None):
    """Which endpoint the agy-run leg for a conversation listens on (roster.local_endpoint: pipe on Windows)."""
    return _roster().local_endpoint(f"agy-leg-{conversation_id}", platform)


def rows(path):
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
    """Send one JSON line to the leg and return its one-line JSON answer.

    The Windows pipe read cannot be interrupted, so it runs in a daemon thread
    abandoned after `timeout`.
    """
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
            if r.get("source") == "MODEL" and r.get("type") == "PLANNER_RESPONSE" \
                    and r.get("content") and not r.get("tool_calls"):
                return r["content"]
        if loop.time() >= deadline:
            return NO_REPLY
        await asyncio.sleep(interval)


NO_LEG = ("[unimatrix-peer-agy] not delivered: this agy conversation has no leg endpoint. The SessionStart "
          "hook normally starts it; if this session predates the hook, ask the agy user to let it run any "
          "shell command (run_command), then resend.")
QUEUED = ("[unimatrix-peer-agy] queued: the agy leg is not live yet and spooled the message; it is delivered "
          "when the agy session's first shell command (run_command) brings the leg up. No reply is awaited.")


async def agy_turn(leg_sock, transcript_path, text, timeout=600, interval=1.0):
    """What did agy answer to `text`: baseline the transcript, deliver via the leg, return the reply."""
    baseline = len(rows(transcript_path))
    try:
        ack = await asyncio.to_thread(to_leg, leg_sock, text)
    except (FileNotFoundError, ConnectionRefusedError):
        return NO_LEG
    if not ack.get("ok"):
        return f"[unimatrix-peer-agy] delivery failed: {ack}"
    if ack.get("queued"):
        return QUEUED
    return await await_reply(transcript_path, baseline, timeout, interval)


def main(argv=None):
    """`unimatrix-peer-agy.py <conversation-id> <text>`: one turn into the conversation; prints the reply."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 2:
        sys.exit("usage: unimatrix-peer-agy.py <conversation-id> <text>")
    conv, text = argv
    print(asyncio.run(agy_turn(leg_endpoint(conv), transcript_path(conv), text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
