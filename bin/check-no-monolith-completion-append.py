# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import os
import sys


def _import_run_op_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def _default_coordinator_root() -> str:
    # Mirrors the retired bash script's own default: SCRIPT_DIR=dirname(script)
    # (bin/), COORDINATOR_ROOT=dirname(SCRIPT_DIR) (coordinator/).
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def _argv_with_default_root(argv: list) -> list:
    if "--root" in argv or "--help" in argv or "-h" in argv:
        return argv
    return ["--root", _default_coordinator_root()] + argv


def main(argv: "list[str] | None" = None) -> int:
    try:
        run_op_main = _import_run_op_main()
    except RuntimeError as exc:
        print(
            f"check-no-monolith-completion-append.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        return 2
    except ImportError as exc:
        print(
            f"check-no-monolith-completion-append.py: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        code = run_op_main(
            "coordinator_core.ops.check_no_monolith_completion_append",
            _argv_with_default_root((sys.argv[1:] if argv is None else argv)),
        )
    except ImportError as exc:
        print(
            "check-no-monolith-completion-append.py: "
            f"coordinator_core.ops.check_no_monolith_completion_append not importable: {exc}",
            file=sys.stderr,
        )
        return 2

    return code


if __name__ == "__main__":
    sys.exit(main())
