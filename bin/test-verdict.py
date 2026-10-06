"""test-verdict.py — thin door-served CLI over `coordinator_core.ops.verdict_record_op`.

`main(argv)` shim, `reverify-delivery.py` shape: engine imports happen inside `main()`, the module
body stays pure.

Usage:
  python test-verdict.py record --result-json JSON_OR_PATH [--repo-root PATH] [--plan PATH]

Exit codes: 0 recorded, 1 refused, 2 coordinator_core unresolvable.
"""
from __future__ import annotations

import sys


def main(argv: "list[str] | None" = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.cli_entry import run_op_main
    except Exception as exc:
        print(
            f"test-verdict.py: ERROR — coordinator_core unresolvable: {exc}",
            file=sys.stderr,
        )
        return 2

    return run_op_main("coordinator_core.ops.verdict_record_op", args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
