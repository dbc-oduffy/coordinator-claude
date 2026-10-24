"""machine-local.py — door-eligible engine entrypoint for `machine-local`.

Trampoline into the full implementation at
`coordinator/templates/bin/_machine_local.py` (all verbs, not a subset). The
door resolves `{engine_root}/coordinator/bin/<name>.py`; this is that file.

No `exec` hop: the door's interpreter is the engine's own.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[1] / "templates" / "bin" / "_machine_local.py"


def _load_impl():
    spec = importlib.util.spec_from_file_location("_machine_local", _IMPL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _code(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    print(value, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run machine-local; argv excludes the program name. Returns the exit code."""
    impl = _load_impl()
    saved = sys.argv
    if argv is not None:
        sys.argv = ["machine-local", *argv]
    try:
        return _code(impl.main())
    except SystemExit as exc:
        return _code(exc.code)
    finally:
        sys.argv = saved


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
