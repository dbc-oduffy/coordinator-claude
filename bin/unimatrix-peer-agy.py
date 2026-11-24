#!/usr/bin/env python3
"""agy peer adapter: deliver one turn to a live agy conversation through its agy-run leg
(unimatrix-agy-leg.py) and read the reply from the conversation transcript.

Thin CLI wrapper + re-export facade over `_unimatrix.adapters.agy`.
"""
import asyncio
import importlib
import importlib.util
import os
import sys
from pathlib import Path

_CORE = None


def _agy():
    global _CORE
    if _CORE is None:
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        if "_unimatrix" not in sys.modules and bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        _CORE = importlib.import_module("_unimatrix.adapters.agy")
    return _CORE


def __getattr__(name):
    return getattr(_agy(), name)


def _roster():
    spec = importlib.util.spec_from_file_location(
        "unimatrix_roster", Path(__file__).resolve().with_name("unimatrix-roster.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def leg_endpoint(conversation_id, platform=None):
    """Which endpoint the agy-run leg for a conversation listens on (roster.local_endpoint: pipe on Windows)."""
    return _roster().local_endpoint(f"agy-leg-{conversation_id}", platform)


async def agy_turn(leg_sock, tpath, text, timeout=600, interval=1.0, wait_reply=True):
    """What did agy answer to `text`: baseline the transcript, deliver via the leg, return the reply."""
    mod = _agy()
    sender = globals().get("to_leg") or mod.to_leg
    return await mod.agy_turn(leg_sock, tpath, text, timeout=timeout, interval=interval, sender=sender,
                             wait_reply=wait_reply)


def main(argv=None):
    """`unimatrix-peer-agy.py <conversation-id> <text>`: one turn into the conversation; prints the reply."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 2:
        sys.exit("usage: unimatrix-peer-agy.py <conversation-id> <text>")
    conv, text = argv
    tpath_fn = globals().get("transcript_path") or _agy().transcript_path
    print(asyncio.run(agy_turn(leg_endpoint(conv), tpath_fn(conv), text)))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-peer-agy [-h]\nunimatrix Antigravity peer")
        raise SystemExit(0)
    sys.exit(main())
