#!/usr/bin/env python3
"""gem-save-box — thin CLI over `coordinator/bin/lib/gem_save_box.py`.

The Group EM's "save the box by killing stuff" button: stops literal integer PIDs (optionally with
their descendants) and carries no kill verb in any shell command. All logic lives in the imported
module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BIN_LIB_DIR = Path(__file__).resolve().parent / "lib"


def _gem_save_box():
    """`gem_save_box`, imported on first use so a bare import of this module leaves `sys.path`
    untouched."""
    if str(_BIN_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_LIB_DIR))
    import gem_save_box

    return gem_save_box


def main(argv=None) -> int:
    return _gem_save_box().main(sys.argv[1:] if argv is None else list(argv))


if __name__ == "__main__":
    sys.exit(main())
