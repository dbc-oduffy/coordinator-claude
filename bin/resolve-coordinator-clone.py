"""resolve-coordinator-clone.py -- door-resolvable entrypoint over coordinator/lib/resolve-coordinator-clone.py.

The lib file is the implementation; this file only gives the static-family name an
engine entrypoint at coordinator/bin. Flags and exit codes (0, 1, 2) are the lib's own.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LIB_PATH = Path(__file__).resolve().parents[1] / "lib" / "resolve-coordinator-clone.py"


def _load_lib():
    spec = importlib.util.spec_from_file_location("_resolve_coordinator_clone_lib", _LIB_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    lib = _load_lib()
    if args and args[0] in ("--help", "-h"):
        sys.stdout.write(lib._USAGE)
        return 0
    return lib.main(args)


if __name__ == "__main__":
    sys.exit(main())
