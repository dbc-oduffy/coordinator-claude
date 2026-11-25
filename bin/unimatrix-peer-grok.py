#!/usr/bin/env python3
"""Grok adapter for the unimatrix peer router: registry discovery and agent-mail delivery.

Thin CLI wrapper + re-export facade over `_unimatrix.adapters.grok` and `_unimatrix.proc`.
"""
import asyncio
import importlib
import json
import os
import subprocess  # noqa: F401 -- exposed for tests patching subprocess.run
import sys

_GROK = None
_PATHS = None
_PROC = None


def _ensure_pkg():
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)


def _grok():
    global _GROK
    if _GROK is None:
        _ensure_pkg()
        _GROK = importlib.import_module("_unimatrix.adapters.grok")
    return _GROK


def _paths():
    global _PATHS
    if _PATHS is None:
        _ensure_pkg()
        _PATHS = importlib.import_module("_unimatrix.paths")
    return _PATHS


def _proc():
    global _PROC
    if _PROC is None:
        _ensure_pkg()
        _PROC = importlib.import_module("_unimatrix.proc")
    return _PROC


def __getattr__(name):
    if name in ("_parent_pid_windows", "parent_pid"):
        return getattr(_proc(), name)
    if name == "_default_pid_alive":
        return _proc().pid_alive
    return getattr(_grok(), name)


def _contract():
    return _paths()


def main(argv=None) -> int:
    """`unimatrix-peer-grok.py <session-id> <cwd> <text>`: agent mail, or a failure string."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 3:
        sys.exit("usage: unimatrix-peer-grok.py <session-id> <cwd> <text>")
    result = asyncio.run(_grok().deliver(*argv))
    print(result if isinstance(result, str) else json.dumps(result))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-peer-grok [-h]\nunimatrix Grok peer")
        raise SystemExit(0)
    sys.exit(main())
