#!/usr/bin/env python3
"""agy SessionStart hook: register the conversation's leg at boot.

agy's SessionStart env carries only ANTIGRAVITY_CONVERSATION_ID, not ANTIGRAVITY_CSRF_TOKEN, so the
leg starts pending: it binds its endpoint and queues peer messages. The language-server address is
discovered from the agy pid's listening ports. The first run_command through the PreToolUse hook's
rewrite (unimatrix-agy-hook-pretool.py) relaunches the leg live, which drains the queue.

Reads the payload's `conversationId`, takes the agy pid from the nearest agy.exe ancestor of this hook
(agy launches hooks through a short-lived intermediate process, so getppid() is never used; none found
records no agy pid), takes the leg cwd from the payload `cwd` else `workspacePaths[0]`, and runs unimatrix-agy-hook-launch.py's start() in-process; start() spawns the leg detached and writes
the leg record, then the conversation is upserted into peers.json (register_peer, as the Codex hook
does). Where the env does carry the address and token the leg starts live here.

Always exits 0. Prints one JSON object: a plain systemMessage noting registration when a leg record exists afterwards, else `{}`.

unimatrix-agy-hook-launch.py and unimatrix-roster.py are resolved beside this file.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = "agy"
NOTE = "Registered with the unimatrix peer router: Claude/Codex peers can message this session."


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def payload_cwd(payload):
    """Payload `cwd` when a non-empty string, else the first non-empty string of `workspacePaths`, else None."""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    paths = payload.get("workspacePaths")
    first = paths[0] if isinstance(paths, list) and paths else None
    return first if isinstance(first, str) and first else None


def register(payload, agy_pid):
    """Start the leg for payload's conversation; True when a leg record for it exists afterwards."""
    if not isinstance(payload, dict):
        return False
    launch = load_sibling("unimatrix-agy-hook-launch")
    roster = launch.load_sibling("unimatrix-roster")
    conv = payload.get("conversationId") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    state = roster.settings_home() / "unimatrix" / "agy-legs"
    cwd = payload_cwd(payload)
    launch.start({"conversationId": conv, "agyPid": agy_pid, "cwd": cwd}, roster, state)
    registered = isinstance(conv, str) and bool(launch.CONV_RE.match(conv)) and (state / f"{conv}.json").is_file()
    if registered:
        bind_peer(conv, state / f"{conv}.json")
    return registered


def bind_peer(conv, record):
    """Upsert this conversation into peers.json as an agy peer, named as the router names a leg record.

    Never raises: the leg record already registers the peer with the router, so a peers.json
    failure (lock timeout, conflicting alias) only loses the durable row.
    """
    try:
        router = load_sibling("unimatrix-peer-router")
        cwd = json.loads(record.read_text(encoding="utf-8")).get("cwd")
        name = router.readable_peer_name(VENDOR, conv, cwd)
        return load_sibling("unimatrix-codex-hook-sessionstart").register_peer(
            router.default_peers_file(), name, VENDOR, conv)
    except Exception:
        return None


def reply(registered, worker_pointer=None):
    # Trap: agy (observed 2026-11-04) panics "cannot convert string to message" on a SessionStart
    # systemMessage carrying metadata.user_markdown, despite its own docs; notes go as plain text.
    notes = ([NOTE] if registered else []) + ([worker_pointer] if worker_pointer else [])
    return {"injectSteps": [{"systemMessage": {"systemMessage": n}} for n in notes]} if notes else {}


def main():
    out = {}
    try:
        payload = json.load(sys.stdin)
        try:
            pointer = load_sibling("unimatrix-codex-hook-sessionstart").worker_pointer()
        except Exception:
            pointer = None
        try:
            registered = register(payload, load_sibling("unimatrix-agy-hook-pretool").agy_ancestor_pid())
        except Exception:
            registered = False
        out = reply(registered, pointer)
    except Exception:
        out = {}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-agy-hook-sessionstart [-h]\nAntigravity SessionStart hook body; reads hook JSON on stdin, emits JSON")
        raise SystemExit(0)
    sys.exit(main())
