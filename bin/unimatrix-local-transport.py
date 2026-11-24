"""Local JSON-line transport: private Unix sockets and native Windows named pipes.

Thin facade over `_unimatrix.transport` preserving every public symbol.
"""
import importlib
import os
import sys

_CORE = None


def _transport():
    global _CORE
    if _CORE is None:
        bin_dir = os.path.dirname(os.path.abspath(__file__))
        if "_unimatrix" not in sys.modules and bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        _CORE = importlib.import_module("_unimatrix.transport")
    return _CORE


def __getattr__(name):
    return getattr(_transport(), name)
