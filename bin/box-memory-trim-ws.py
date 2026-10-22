#!/usr/bin/env python3
"""box-memory-trim-ws.py PID -- trim one process's working set (Windows only).

Prints one line on success, exit 0:
  TRIMMED pid=N wset=<before>MB-><after>MB
Access denied or a gone pid: one stderr line, exit 1. Non-Windows host: exit 6.
The working-set sizes read `?` when psutil is absent.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Callable, Optional

PROG = "box-memory-trim-ws"


def _load_host():
    path = Path(__file__).resolve().parent / "lib" / "box_memory_host.py"
    spec = importlib.util.spec_from_file_location("box_memory_host", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # the host's @dataclass classes resolve annotations through it
    spec.loader.exec_module(module)
    return module


def read_wset_mb(pid: int) -> Optional[int]:
    try:
        import psutil

        info = psutil.Process(pid).memory_info()
        return int(getattr(info, "wset", info.rss) // (1024 * 1024))
    except Exception:
        return None


def _fmt(mb: Optional[int]) -> str:
    return "?" if mb is None else str(mb)


def main(
    argv: Optional[list] = None,
    *,
    platform: Optional[str] = None,
    trim: Optional[Callable[[int], None]] = None,
    reader: Callable[[int], Optional[int]] = read_wset_mb,
) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description="Trim one process's working set.")
    parser.add_argument("pid", type=int, help="target process id")
    args = parser.parse_args(argv)

    host = _load_host()
    plat = platform if platform is not None else sys.platform
    if plat != "win32":
        return host.unsupported(PROG, plat, "working-set trim needs Windows")
    trim_fn = trim if trim is not None else host.empty_working_set
    before = reader(args.pid)
    try:
        trim_fn(args.pid)
    except OSError as exc:
        print(f"{PROG}: pid={args.pid}: {exc}", file=sys.stderr)
        return 1
    after = reader(args.pid)
    print(f"TRIMMED pid={args.pid} wset={_fmt(before)}MB->{_fmt(after)}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
