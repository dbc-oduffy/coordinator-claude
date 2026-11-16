#!/usr/bin/env python3

from __future__ import annotations

INSTALL_CLASS = True

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.install.uninstall_legs import orchestrate_uninstall as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"coordinator-uninstall.py: engine-root resolution failed: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(
            f"coordinator-uninstall.py: coordinator_core.install.uninstall_legs not importable: {exc}",
            file=sys.stderr,
        )
        return 1
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
