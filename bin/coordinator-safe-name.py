# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-safe-name — CLI wrapper for lib/coordinator_safe_name.py.

Naked-Python port (2026-07-19 Windows de-bash campaign, chunk E3-c). Thin CLI
that resolves the lib path relative to this script's own directory, imports
it, and dispatches timestamp/slug/check subcommands to the csn_* functions.
Windows bare-name invocation is covered by the generated
coordinator-safe-name.cmd launcher (gen-launcher-shim.py), not a shell
shebang trick.

Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § seam 1
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Wave E3-c)

Usage:
  coordinator-safe-name timestamp [--now | --mtime <file>]
  coordinator-safe-name slug "<text>"
  coordinator-safe-name check "<component>"
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    import os

    _bin_dir = os.path.dirname(os.path.abspath(__file__))  # noqa: F841

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_safe_name import main as _sub_main

    return _sub_main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
