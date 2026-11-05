"""Keep every live local session mirrored on the far box: one relay `inbox` client per
session, started when the session appears and tree-killed when it exits.

Usage:
  unimatrix-mirror-all.py <log> [<skip-name> ...] --remote <lan-ssh-alias> [--tunnel-remote <ssh-alias>] [--key <path>]

--remote is tried first; --tunnel-remote (or $UNIMATRIX_TUNNEL_REMOTE) is used only while
--remote does not answer.

Skipped names are mirrored by a client started elsewhere. Our own mirror entries
(those carrying macSocketPath) are never exported back.
"""
import argparse
import importlib.util
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
POLL_SECONDS = 30


def _shared():
    spec = importlib.util.spec_from_file_location("unimatrix_roster", HERE / "unimatrix-roster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ROSTER = None


def _roster():
    """The roster module, loaded on first use: a bin entrypoint stays inert at import."""
    global _ROSTER
    if _ROSTER is None:
        _ROSTER = _shared()
    return _ROSTER


def __getattr__(name):
    if name == "R":
        return _roster()
    raise AttributeError(name)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="unimatrix-mirror-all.py")
    p.add_argument("log")
    p.add_argument("skip", nargs="*", help="session names mirrored by a client started elsewhere")
    p.add_argument("--remote", required=True, help="ssh alias of the far box on the LAN, tried first")
    p.add_argument("--tunnel-remote", default=None, help=f"ssh alias over the tunnel, used only when --remote does not answer (default: ${_roster().TUNNEL_ENV})")
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    a.key = a.key or _roster().default_key()
    a.tunnel_remote = a.tunnel_remote or _roster().default_tunnel()
    return a


def live_sessions(skip):
    sess = _roster().sessions_dir()
    out = {}
    for f in os.listdir(sess):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(sess, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        name = d.get("name")
        if d.get(_roster().FAR_SOCKET_FIELD) or not name or name in skip or not NAME_RE.fullmatch(str(name)):
            continue
        if not isinstance(d.get("pid"), int) or not d.get("messagingSocketPath"):
            continue
        if _roster().pid_alive(d["pid"]):
            out[name] = d
    return out


def inbox_cmd(d, name, log_dir, remote, key, tunnel_remote=None):
    cmd = [sys.executable, str(HERE / "unimatrix-inbox.py"), str(d["pid"]), name,
           os.path.join(log_dir, f"unimatrix-inbox-{name}.log"), d["messagingSocketPath"],
           "--remote", remote, "--key", key]
    return cmd + ["--tunnel-remote", tunnel_remote] if tunnel_remote else cmd


def sync(clients, live, cfg, say):
    """One reconcile pass: `clients` is name -> (session pid, Popen)."""
    log_dir = os.path.dirname(os.path.abspath(cfg.log))
    for name, d in live.items():
        c = clients.get(name)
        if c and c[0] == d["pid"] and c[1].poll() is None:
            continue
        if c:
            _roster().tree_kill(c[1].pid)
        p = _roster().spawn(inbox_cmd(d, name, log_dir, cfg.remote, cfg.key, cfg.tunnel_remote))
        clients[name] = (d["pid"], p)
        say(f"mirror {name} pid {d['pid']} -> client {p.pid}")
    for name in [n for n in clients if n not in live]:
        # The client's ssh child holds the far inbox open; killing python alone orphans it.
        _roster().tree_kill(clients.pop(name)[1].pid)
        say(f"unmirror {name}")


def main(argv=None):
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    skip = set(cfg.skip)
    log = open(cfg.log, "a", encoding="utf-8", buffering=1)

    def say(msg):
        log.write(f"{time.strftime('%H:%M:%SZ', time.gmtime())} {msg}\n")

    if sys.platform != "win32":
        # A stop is never silent: a clean 0 would read as "nothing to mirror" while every mirror drops.
        def stopped(signum, _frame):
            say(f"stopped by signal {signum}; mirrors drop until relaunched")
            sys.exit(128 + signum)
        signal.signal(signal.SIGTERM, stopped)
    clients = {}
    try:
        while True:
            sync(clients, live_sessions(skip), cfg, say)
            time.sleep(POLL_SECONDS)
    finally:
        for _, p in clients.values():
            _roster().tree_kill(p.pid)


if __name__ == "__main__":
    main()
