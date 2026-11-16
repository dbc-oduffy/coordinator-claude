#!/usr/bin/env python3
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
