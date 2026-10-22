"""Turn-state hook for claude-author --control-socket.

Registered per launch through ``--settings`` for SessionStart, UserPromptSubmit and Stop.
``argv[1]`` is the instance directory; the hook JSON arrives on stdin. Writes
``<instance>/turn.json`` atomically. Always exits 0 and prints nothing, so it can never
block or alter a turn. Stdlib only; it must not import the rest of the package.
"""
import json
import os
import sys
from datetime import datetime, timezone

TURN_FILE = "turn.json"  # mirrors protocol.TURN_FILE
_ACTIVE = {"SessionStart": None, "UserPromptSubmit": True, "Stop": False}


def _read_existing(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(instance_dir, payload, now=None):
    """Apply one hook payload to ``turn.json``; returns the state written, or None."""
    event = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if event not in _ACTIVE:
        return None
    path = os.path.join(instance_dir, TURN_FILE)
    prior = _read_existing(path)
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        session_id = prior.get("session_id")
    active = _ACTIVE[event]
    if active is None:
        active = False
    ts = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    state = {"session_id": session_id, "turn_active": active, "event": event, "ts": ts}
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return None
    return state


def main(argv, stdin):
    try:
        if len(argv) < 2:
            return 0
        raw = stdin.read()
        record(argv[1], json.loads(raw))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv, sys.stdin))
