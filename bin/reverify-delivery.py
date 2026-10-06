"""reverify-delivery.py — thin door-served CLI over
`coordinator_core.ops.dispatch_emit.reverify_delivery`.

The published surface probes this exact path; the file name and location stay
fixed. `main(argv)` shim, `emit-dispatch-workflow.py :: main` shape: engine
imports happen inside `main()`, the module body stays pure. Argument parsing and
the delivery-verdict write live in the engine module; this file owns nothing but
the door.

Usage:
  python reverify-delivery.py record --run-record PATH --result-json JSON_OR_PATH [--repo-root PATH] [--session-id ID]

Exit codes: 0 recorded, 1 data error, 2 coordinator_core unresolvable.
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
            f"reverify-delivery.py: ERROR — coordinator_core unresolvable: {exc}",
            file=sys.stderr,
        )
        return 2

    return run_op_main("coordinator_core.ops.dispatch_emit.reverify_delivery", args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
