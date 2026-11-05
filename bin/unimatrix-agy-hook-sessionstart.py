"""agy SessionStart hook: register the conversation's leg at boot.

agy's SessionStart env carries only ANTIGRAVITY_CONVERSATION_ID, not ANTIGRAVITY_CSRF_TOKEN, so the
leg starts pending: it binds its endpoint and queues peer messages. The language-server address is
discovered from the agy pid's listening ports. The first run_command through the PreToolUse hook's
rewrite (unimatrix-agy-hook-pretool.py) relaunches the leg live, which drains the queue.

Reads the payload's `conversationId`, takes the agy pid from os.getppid() (hooks are spawned by agy),
and runs unimatrix-agy-hook-launch.py's start() in-process; start() spawns the leg detached and writes
the leg record. Where the env does carry the address and token the leg starts live here.

Always exits 0. Prints one JSON object: a plain systemMessage noting registration when a leg record exists afterwards, else `{}`.

unimatrix-agy-hook-launch.py and unimatrix-roster.py are resolved beside this file.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTE = "Registered with the unimatrix peer router: Claude/Codex peers can message this session."


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def register(payload, agy_pid):
    """Start the leg for payload's conversation; True when a leg record for it exists afterwards."""
    if not isinstance(payload, dict):
        return False
    launch = load_sibling("unimatrix-agy-hook-launch")
    roster = launch.load_sibling("unimatrix-roster")
    conv = payload.get("conversationId") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    state = roster.settings_home() / "unimatrix" / "agy-legs"
    launch.start({"conversationId": conv, "agyPid": agy_pid}, roster, state)
    return isinstance(conv, str) and bool(launch.CONV_RE.match(conv)) and (state / f"{conv}.json").is_file()


def reply(registered):
    if not registered:
        return {}
    # Trap: agy (observed 2026-11-04) panics "cannot convert string to message" on a SessionStart
    # systemMessage carrying metadata.user_markdown, despite its own docs; the note goes as plain text.
    return {"injectSteps": [{"systemMessage": {"systemMessage": NOTE}}]}


def main():
    out = {}
    try:
        out = reply(register(json.load(sys.stdin), os.getppid()))
    except Exception:
        out = {}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
