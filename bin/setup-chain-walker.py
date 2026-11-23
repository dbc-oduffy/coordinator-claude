#!/usr/bin/env python3
"""setup-chain-walker.py: resolved bin launcher for `coordinator_core.ops.setup_chain_walker`.

Forwards `sys.argv[1:]` verbatim to the walker's `main` in this process and exits
with its return code, so `--coordinator-root PATH` (and every other walker flag)
works through a bare-name launcher. The engine import is lazy: the module body
stays inert.
"""
from __future__ import annotations

INSTALL_CLASS = False  # the launcher writes nothing itself; the walker's own writes are declared on its module

import sys
from collections.abc import Callable

GENERATES = []  # forwards to the walker; this file generates no artifact


def _walker_main() -> Callable[[list[str]], int]:
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.ops import setup_chain_walker

    return setup_chain_walker.main


def main(argv: list[str] | None = None) -> int:
    """Run the walker with `argv` (default `sys.argv[1:]`) unchanged; return its exit code."""
    argv = sys.argv[1:] if argv is None else list(argv)
    return _walker_main()(argv)


if __name__ == "__main__":
    sys.exit(main())
