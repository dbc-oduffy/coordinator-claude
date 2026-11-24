#!/usr/bin/env python3
"""Peer contract shared by the unimatrix peer router and adapters.

Thin inert CLI wrapper + re-export facade over `_unimatrix.protocol` and `_unimatrix.paths`.
"""
import importlib
import os
import socket  # noqa: F401 -- exposed for callers/tests patching socket.gethostname
import sys

_CORE = None
_PATHS = None
_PATH_NAMES = ("box_id", "is_ip_literal", "local_box", "safe_alias")


def _ensure_pkg():
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)


def _protocol():
    global _CORE
    if _CORE is None:
        _ensure_pkg()
        _CORE = importlib.import_module("_unimatrix.protocol")
    return _CORE


def _paths():
    global _PATHS
    if _PATHS is None:
        _ensure_pkg()
        _PATHS = importlib.import_module("_unimatrix.paths")
    return _PATHS


def __getattr__(name):
    if name in _PATH_NAMES:
        return getattr(_paths(), name)
    return getattr(_protocol(), name)


def main(argv=None) -> int:
    """Validate a peers.json: `unimatrix-peer-contract.py <peers.json>` prints each peer or the error."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1:
        print("usage: unimatrix-peer-contract.py <peers.json>", file=sys.stderr)
        return 2
    try:
        peers = _protocol().load_peers(argv[0])
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    for p in peers:
        print(f"{p['name']}\t{p['vendor']}\t{p['target']}")
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-peer-contract [-h]\nunimatrix peer-contract checker; usage: unimatrix-peer-contract <file>")
        raise SystemExit(0)
    sys.exit(main())
