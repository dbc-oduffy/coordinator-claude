"""trim-file-cache — thin CLI over `coordinator/bin/lib/file_cache_trim.py`.

Trims the Windows system file-cache working set to the standby list, on demand. Dry-run by
default; `--apply` performs the trim. All logic lives in the imported module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BIN_LIB_DIR = Path(__file__).resolve().parent / "lib"


def _file_cache_trim():
    """`file_cache_trim`, imported on first use so a bare import of this module leaves
    `sys.path` untouched."""
    if str(_BIN_LIB_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_LIB_DIR))
    import file_cache_trim

    return file_cache_trim


def main(argv=None) -> int:
    return _file_cache_trim().main(sys.argv[1:] if argv is None else list(argv))


if __name__ == "__main__":
    sys.exit(main())
