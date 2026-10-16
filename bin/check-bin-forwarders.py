"""
check-bin-forwarders.py -- CLI trampoline over coordinator_core.plugin_health.doe_bin_forwarders.

Exit 0 when every DoE coordinator/bin/*.py the engine also owns, bar the names in
doe_bin_forwarders.DOE_LIVE, is a canonical forwarder, or the DoE clone is unresolvable;
exit 1 listing offenders.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-bin-forwarders",
        description="Fail when a DoE coordinator/bin/*.py the engine also owns regrew logic.",
    )
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.plugin_health.doe_bin_forwarders import main as op_main
    except RuntimeError as exc:
        print(f"check-bin-forwarders: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 0
    except ImportError as exc:
        print(f"check-bin-forwarders: doe_bin_forwarders not importable: {exc}", file=sys.stderr)
        return 0
    return op_main([])


if __name__ == "__main__":
    sys.exit(main())
