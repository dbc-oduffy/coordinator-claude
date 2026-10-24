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
import time
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


def _win_procs(gov, root_pid: int, proc_table_fn, cmdline_fn) -> list:
    """Windows process list from one table read; a command line is read only for the root's tree.

    Every row is built with cmd="", the tree is walked on pid/ppid alone, then each tree member is
    rebuilt with its real command line so is_protected sees it. Rows outside the tree keep cmd="".
    """
    now = time.time()
    procs = [
        gov.Proc(r.pid, r.ppid, max(0.0, now - r.create_time) if r.create_time else 0.0,
                 r.working_set_bytes / 1048576, "")
        for r in proc_table_fn()
    ]
    members = set(gov.descendants(root_pid, procs))
    return [
        gov.Proc(p.pid, p.ppid, p.age_s, p.rss_mb, cmdline_fn(p.pid)) if p.pid in members else p
        for p in procs
    ]


def main(
    argv: Optional[list] = None,
    *,
    governor=None,
    platform: Optional[str] = None,
    proc_table_fn=None,
    cmdline_fn=None,
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

    if plat == "win32":
        procs = _win_procs(
            gov,
            args.pid,
            proc_table_fn if proc_table_fn is not None else host.proc_table,
            cmdline_fn if cmdline_fn is not None else host.proc_cmdline,
        )
    else:
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
