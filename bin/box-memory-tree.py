#!/usr/bin/env python3
"""box-memory-tree.py {suspend,resume} PID -- suspend or resume a whole process tree.

Prints one line on stdout, exit 0:
  SUSPENDED pid=N tree=K skipped=S
  RESUMED pid=N tree=K skipped=S
`tree` counts the processes signalled (root included); `skipped` counts protected descendants
left untouched. A protected or absent root refuses with one stderr line, exit 1. There is no
kill path. The tree walk and the signalling come from the governor through load_governor.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Optional

PROG = "box-memory-tree"


def _load_host():
    path = Path(__file__).resolve().parent / "lib" / "box_memory_host.py"
    spec = importlib.util.spec_from_file_location("box_memory_host", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # the host's @dataclass classes resolve annotations through it
    spec.loader.exec_module(module)
    return module


def main(
    argv: Optional[list] = None,
    *,
    governor=None,
    platform: Optional[str] = None,
) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description="Suspend or resume a process tree.")
    parser.add_argument("action", choices=["suspend", "resume"])
    parser.add_argument("pid", type=int, help="root process id of the tree")
    args = parser.parse_args(argv)

    host = _load_host()
    plat = platform if platform is not None else sys.platform
    if plat == "win32":
        missing = host.require_psutil(PROG)
        if missing is not None:
            return missing
    gov = governor if governor is not None else host.load_governor()

    procs = gov.list_procs()
    by_pid = {p.pid: p for p in procs}
    root = by_pid.get(args.pid)
    if root is None:
        print(f"{PROG}: pid={args.pid}: no such process", file=sys.stderr)
        return 1
    if gov.is_protected(root):
        print(f"{PROG}: pid={args.pid}: protected process, refusing", file=sys.stderr)
        return 1

    tree = gov.descendants(args.pid, procs)
    targets = [pid for pid in tree if pid in by_pid and not gov.is_protected(by_pid[pid])]
    skipped = len([pid for pid in tree if pid in by_pid]) - len(targets)
    stop = args.action == "suspend"
    gov.signal_tree(targets, stop)
    word = "SUSPENDED" if stop else "RESUMED"
    print(f"{word} pid={args.pid} tree={len(targets)} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
