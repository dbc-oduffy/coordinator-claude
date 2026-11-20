#!/usr/bin/env python3
"""Run coordinator_core.tui_status for one host: `unimatrix-tui-status-launch.py <engine-root> <host>`.

The status-line command of agy and Grok runs from a cwd with no coordinator_core on sys.path and
may not carry a space or quote inside any argument (agy's Windows statusline runner splits a `-c`
one-liner), so the engine root rides in argv and is put on sys.path first.
"""
import runpy
import sys

TUI_STATUS_MODULE = "coordinator_core.tui_status"


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    usage = "usage: unimatrix-tui-status-launch.py <engine-root> <host>"
    if args[:1] in (["--help"], ["-h"]):
        print(usage)
        return 0
    if len(args) < 2:
        print(usage, file=sys.stderr)
        return 2
    sys.path.insert(0, args[0])
    sys.argv = [sys.argv[0], *args[1:]]
    runpy.run_module(TUI_STATUS_MODULE, run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
