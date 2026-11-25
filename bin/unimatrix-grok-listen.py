#!/usr/bin/env python3
"""Print agent mail for one Grok session. A monitor reads each line; nothing is typed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _unimatrix.adapters.grok import serve_inbox  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 2 or argv[0] != "--session-id" or not argv[1]:
        sys.exit("usage: unimatrix-grok-listen.py --session-id <session-id>")
    serve_inbox(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
