#!/usr/bin/env python3
"""machine-local.py — door-eligible, warm-servable entrypoint for `machine-local`.

Trampoline into the full implementation at
`coordinator/templates/bin/_machine_local.py` (all verbs, not a subset). The
door resolves `{engine_root}/coordinator/bin/<name>.py`; this is that file.

Warm-served, the kernel is loaded once per process and reused. Its watchdog and
scan budget are armed only by its own `__main__` block, and the watchdog's
`os._exit` must never run inside a shared server, so `main` arms the in-process
budget per read call and clears it afterwards. A blocking syscall cannot be
preempted in-process: that stall ends at the door's own deadline, not here.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[1] / "templates" / "bin" / "_machine_local.py"
_READ_VERBS = frozenset({"get", "require", "has", "path", "dir", "dump", "keys"})
_impl = None


def _load_impl():
    """Return the kernel module, loading it on first use (memoized per process)."""
    global _impl
    if _impl is None:
        spec = importlib.util.spec_from_file_location("_machine_local", _IMPL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _impl = module
    return _impl


def _code(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    print(value, file=sys.stderr)
    return 1


def _deadline_seconds(impl) -> float:
    raw = os.environ.get("MACHINE_LOCAL_DEADLINE_S")
    try:
        return float(raw) if raw else impl._BACKSTOP_S
    except ValueError:
        return impl._BACKSTOP_S


def main(argv: list[str] | None = None) -> int:
    """Run machine-local; argv excludes the program name. Returns the exit code."""
    saved = sys.argv
    if argv is not None:
        sys.argv = ["machine-local", *argv]
    impl = None
    try:
        impl = _load_impl()
        if sys.argv[1:2] and sys.argv[1] in _READ_VERBS:
            seconds = _deadline_seconds(impl)
            impl._scan_budget_s = impl._SCAN_BUDGET_S
            if seconds > 0:
                impl._deadline_at = time.monotonic() + seconds
        return _code(impl.main())
    except SystemExit as exc:
        return _code(exc.code)
    finally:
        if impl is not None:
            impl._scan_budget_s = None
            impl._deadline_at = None
        sys.argv = saved


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
