"""targeted-test-run — run only the tests covering one backlog row and what its fixer touched.

Usage: `targeted-test-run --repo <root> --row <row yaml> [--touched <path> ...] --record <path>`.
Selects the row's failing test file plus covering tests of touched files (files only), admits the
argv through the Tier-T classifier, runs it under one Tier-T slot, and writes a `.tests.json` record.
Exit: 0 passed, 1 failed, 3 nothing-to-run, 4 refused, 5 no-runner, 2 usage.
"""
from __future__ import annotations

import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.bug_blitz.targeted_run import main

    return main


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if any(a in ("-h", "--help") for a in args):
        print((__doc__ or "").strip())
        return 0
    try:
        run = _import_main()
    except (RuntimeError, ImportError) as exc:
        print(f"targeted-test-run: engine unavailable: {exc}", file=sys.stderr)
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
