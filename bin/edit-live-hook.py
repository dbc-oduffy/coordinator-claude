# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

import os
import sys

EXIT_TRANSPORT_FAILURE = 3


def _import_runner():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main(argv: "list[str] | None" = None) -> int:
    # EDIT_LIVE_HOOK_SCRIPT_DIR tells the ported module where THIS trampoline
    # `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`. Only set if unset, so
    os.environ.setdefault(
        "EDIT_LIVE_HOOK_SCRIPT_DIR", os.path.dirname(os.path.abspath(__file__))
    )

    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(f"edit-live-hook.sh: engine-root resolution failed: {exc}", file=sys.stderr)
        return EXIT_TRANSPORT_FAILURE
    except ImportError as exc:
        print(
            f"edit-live-hook.sh: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    try:
        code = run_op_main("coordinator_core.ops.edit_live_hook", (sys.argv[1:] if argv is None else argv))
    except ImportError as exc:
        print(
            f"edit-live-hook.sh: coordinator_core.ops.edit_live_hook not importable: {exc}",
            file=sys.stderr,
        )
        return EXIT_TRANSPORT_FAILURE

    return code


if __name__ == "__main__":
    sys.exit(main())
