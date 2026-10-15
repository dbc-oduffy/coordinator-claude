"""workday-start-run — launch or finish one deterministic workday-start run.

Thin entrypoint: resolves the engine and calls `coordinator_core.workday_start.cli.main`.
Usage: `workday-start-run launch` | `workday-start-run finish --run-id <id> [--agent-results <path>]`.
"""
from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.workday_start.cli import main

    return main


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if any(a in ("-h", "--help") for a in args):
        print((__doc__ or "").strip())
        return 0
    try:
        run = _import_main()
    except (RuntimeError, ImportError) as exc:
        print(f"workday-start-run: engine unavailable: {exc}", file=sys.stderr)
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
