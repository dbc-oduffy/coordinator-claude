"""ceremony-run — launch or finish one registered ceremony run.

Thin entrypoint: resolves the engine and calls `coordinator_core.ceremony_common.run.cli.main`.
Usage: `ceremony-run <ceremony> launch [flags]` | `ceremony-run <ceremony> finish --run-id <id> [--agent-results <path>]`.
"""
from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.ceremony_common.run.cli import main

    return main


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if any(a in ("-h", "--help") for a in args):
        print((__doc__ or "").strip())
        return 0
    try:
        run = _import_main()
    except (RuntimeError, ImportError) as exc:
        print(f"ceremony-run: engine unavailable: {exc}", file=sys.stderr)
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
