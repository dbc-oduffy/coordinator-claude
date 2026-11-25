#!/usr/bin/env python3
"""Start the shipped agy leg for one conversation, replacing a stale one.

Run in the declared agy sidecar (unimatrix-agy-sidecar.py, in-process) and inside an agy run_command
(prefixed by unimatrix-agy-hook-pretool.py), where it and the leg inherit agy's language-server address
and token and the leg starts live, replacing a pending one; run by the SessionStart hook without
credentials, the leg starts pending (queuing peer messages, no recorded address). Input:
`--conversation <id> --agy-pid <pid>`, else one JSON object on stdin {"conversationId", "agyPid"}.
The record it writes (see the pretool hook's docstring) stamps the agy pid and LS address the leg
was started under; the pretool hook compares against them.
Never fails the agent's command: every path exits 0 silently.

unimatrix-agy-leg.py and unimatrix-roster.py are resolved beside this file, so it runs from
coordinator/bin and from the installed <settings home>/unimatrix copy alike.
"""
import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONV_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def detach_kwargs():
    """Popen kwargs that leave the child running after agy's run_command shell exits."""
    if os.name == "nt":
        flags = 0
        for name in ("CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):  # never DETACHED_PROCESS: test_no_detached_process_spawn
            flags |= getattr(subprocess, name, 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def write_record(record, data):
    tmp = Path(f"{record}.tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, record)


def read_request(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--conversation")
    ap.add_argument("--agy-pid", type=int)
    ns, _ = ap.parse_known_args(argv)
    if ns.conversation:
        return {"conversationId": ns.conversation, "agyPid": ns.agy_pid}
    try:
        req = json.load(sys.stdin)
    except ValueError:
        return {}
    return req if isinstance(req, dict) else {}


def start(req, roster, state):
    """Start the leg: live when the env carries the token and LS address, else pending (queues messages)."""
    conv = req.get("conversationId") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    if not isinstance(conv, str) or not CONV_RE.match(conv):
        return
    ls = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
    live = bool(ls and os.environ.get("ANTIGRAVITY_CSRF_TOKEN"))
    env = dict(os.environ, ANTIGRAVITY_CONVERSATION_ID=conv)
    if not live:
        env.pop("ANTIGRAVITY_CSRF_TOKEN", None)  # a token without an LS address would make a live leg with no target
    state.mkdir(parents=True, exist_ok=True)
    record = state / f"{conv}.json"
    try:
        old = json.loads(record.read_text())
        old_alive = roster.pid_alive(int(old["pid"]))
        old_live = old.get("mode", "live") == "live"
        old_ep = old.get("endpoint")
        old_ep_ok = os.name == "nt" or not (isinstance(old_ep, str) and os.path.isabs(old_ep)) or os.path.exists(old_ep)
        if old_alive and old_ep_ok and live and old_live and old.get("ls_address") == ls:
            if old.get("agy_pid") != req.get("agyPid"):  # stamp it, or the hook asks again every call
                write_record(record, dict(old, agy_pid=req.get("agyPid")))
            return  # already current for this language server
        if old_alive and old_ep_ok and not live and old.get("agy_pid") == req.get("agyPid"):
            return  # a pending start never replaces a leg of this agy process, live or pending
        if old_alive:
            os.kill(int(old["pid"]), signal.SIGTERM)  # stale, or pending being made live
    except (OSError, ValueError, KeyError, TypeError):
        pass
    ep = roster.local_endpoint(f"agy-leg-{conv}")
    env["AGY_LEG_LOG"] = str(state / f"{conv}.log")
    if isinstance(req.get("agyPid"), int) and req["agyPid"] > 0:
        env["AGY_LEG_PARENT_PID"] = str(req["agyPid"])  # the leg exits when this agy does
    p = subprocess.Popen([roster.console_python(), str(HERE / "unimatrix-agy-leg.py"), ep], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **detach_kwargs())
    write_record(record, {"pid": p.pid, "conversation": conv, "endpoint": ep, "ls_address": ls,
                          "cwd": req.get("cwd") or os.getcwd(), "agy_pid": req.get("agyPid"), "mode": "live" if live else "pending"})


def main(argv=None):
    try:
        roster = load_sibling("unimatrix-roster")
        start(read_request(sys.argv[1:] if argv is None else argv), roster,
              roster.settings_home() / "unimatrix" / "agy-legs")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
