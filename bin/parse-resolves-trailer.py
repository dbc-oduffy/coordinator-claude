#!/usr/bin/env python3

from __future__ import annotations

import os
import sys

def _prepare_claude_klabauter_root() -> None:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()


def main(argv: "list[str] | None" = None) -> int:
    try:
        _prepare_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"parse-resolves-trailer.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 2

    from coordinator_core.cli_entry import run_op_main

    try:
        code = run_op_main("coordinator_core.ops.parse_resolves_trailer", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"parse-resolves-trailer.py: coordinator_core.ops.parse_resolves_trailer not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
