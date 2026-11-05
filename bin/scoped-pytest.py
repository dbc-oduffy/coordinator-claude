"""scoped-pytest — run one named test file or node id under the scoped admission.

Usage: `scoped-pytest --allow <file> [--allow <file> ...] -- <pytest args and targets>`.
Runs from any cwd; the engine is bootstrapped, so a consumer repo needs no PYTHONPATH.
Exit: pytest's own; 75 admission refused; 64 target outside --allow or none named; 137 ancestor died.
"""
from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.testing.scoped_pytest import main

    return main


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if any(a in ("-h", "--help") for a in args):
        print((__doc__ or "").strip())
        return 0
    try:
        run = _import_main()
    except (RuntimeError, ImportError) as exc:
        print(f"scoped-pytest: engine unavailable: {exc}", file=sys.stderr)
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
