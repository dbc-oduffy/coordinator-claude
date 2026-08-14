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

import os
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from coordinator_safe_name import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
