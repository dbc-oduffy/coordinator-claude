"""Restart one far-session bridge on a harness-shaped endpoint (cc-msg-<md5 hex>), then
repoint its session registry entry, procStart and key file at the new bridge.

Usage:
  unimatrix-reshape.py <old-bridge-pid> <log> [--return-port <port> --inbox <endpoint>]
                       --remote <ssh-alias> [--key <path>]

Validates the old entry and its key file before stopping anything. The old bridge is
tree-killed with the same helper unimatrix-roster.py uses.
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


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
    p = argparse.ArgumentParser(prog="unimatrix-reshape.py")
    p.add_argument("old_pid", type=int)
    p.add_argument("log")
    p.add_argument("--return-port", type=int, default=None)
    p.add_argument("--inbox", default=None, help="local inbox endpoint for the return leg")
    p.add_argument("--remote", required=True, help="ssh alias of the far box")
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    if (a.return_port is None) != (a.inbox is None):
        p.error("--return-port and --inbox go together")
    a.key = a.key or _roster().default_key()
    return a


def reshape(cfg, settle_seconds=2):
    sess = _roster().sessions_dir()
    old_json = os.path.join(sess, f"{cfg.old_pid}.json")
    with open(old_json, encoding="utf-8") as fh:
        d = json.load(fh)
    far_sock = d.get(_roster().FAR_SOCKET_FIELD)
    if not far_sock:
        sys.exit(f"reshape: pid {cfg.old_pid} is not a mirror entry")
    keys = [f for f in os.listdir(sess) if f.startswith(f"{cfg.old_pid}.") and f.endswith(".key")]
    if len(keys) != 1:
        sys.exit(f"reshape: expected one key file for pid {cfg.old_pid}, found {len(keys)}")

    endpoint = _roster().local_endpoint(far_sock)
    if sys.platform != "win32":
        os.makedirs(os.path.dirname(endpoint), mode=0o700, exist_ok=True)
    _roster().tree_kill(cfg.old_pid)
    b = _roster().spawn(_roster().bridge_cmd(endpoint, cfg.log, cfg.remote, cfg.key, cfg.return_port, cfg.inbox))
    time.sleep(settle_seconds)
    d.update(pid=b.pid, procStart=_roster().proc_start(b.pid), messagingSocketPath=endpoint)
    _roster().write_json_atomic(os.path.join(sess, f"{b.pid}.json"), d)
    os.remove(old_json)
    os.replace(os.path.join(sess, keys[0]), os.path.join(sess, _roster().key_name(b.pid, endpoint)))
    return f"{d.get('name')}: {cfg.old_pid} -> {b.pid} on {endpoint}"


def main(argv=None):
    print(reshape(parse_args(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    main()
